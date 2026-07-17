from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import time
from typing import Any, Dict

import pytest

from remote_runner.errors import RemoteRunnerError
from remote_runner.errors import StateError

SUCCESS_BOOTSTRAP = """
import time

def bootstrap(session):
    result = session.send("printf 'BOOTSTRAP_VISIBLE\\\\n'")
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        observed = session.read(result["read_from_cursor"], 4096)
        if b"BOOTSTRAP_VISIBLE" in observed.output:
            return
        time.sleep(0.02)
    raise RuntimeError("visible bootstrap output did not arrive")
"""


def test_bootstrap_uses_the_same_terminal_interface(
    rr_env: Dict[str, Any], tmp_path: Path, wait_for_output
) -> None:
    manager = rr_env["manager"]
    hook = tmp_path / "success.py"
    hook.write_text(SUCCESS_BOOTSTRAP, encoding="utf-8")
    manager.instances.add("gpu", str(hook))

    created = manager.create(
        name="bootstrapped",
        shell=rr_env["shell"],
        instance_name="gpu",
        bootstrap_timeout=5,
    )

    assert created["bootstrap_status"] == "succeeded"
    assert created["instance_name"] == "gpu"
    assert Path(created["bootstrap_log_path"]).exists()
    assert not rr_env["store"].bootstrap_result_path(created["session_id"]).exists()
    assert b"BOOTSTRAP_VISIBLE" in wait_for_output(manager, "bootstrapped", b"BOOTSTRAP_VISIBLE")


def test_bootstrap_failure_preserves_live_session_and_diagnostic(
    rr_env: Dict[str, Any], tmp_path: Path, wait_for_output
) -> None:
    manager = rr_env["manager"]
    hook = tmp_path / "failure.py"
    hook.write_text(
        "def bootstrap(session):\n"
        "    session.send(\"printf 'BEFORE_FAILURE\\\\n'\")\n"
        "    raise RuntimeError('login rejected')\n",
        encoding="utf-8",
    )
    manager.instances.add("failing", str(hook))

    with pytest.raises(RemoteRunnerError) as caught:
        manager.create(
            name="failed-bootstrap",
            shell=rr_env["shell"],
            instance_name="failing",
            bootstrap_timeout=5,
        )

    assert caught.value.code == "bootstrap_failed"
    session_id = caught.value.context["session_id"]
    state = manager.show(session_id)
    assert state["session_status"] == "active"
    assert state["bootstrap_status"] == "failed"
    assert Path(caught.value.context["diagnostic_path"]).exists()
    assert b"BEFORE_FAILURE" in wait_for_output(manager, session_id, b"BEFORE_FAILURE")


def test_bootstrap_timeout_terminates_worker_and_leaves_session(
    rr_env: Dict[str, Any], tmp_path: Path
) -> None:
    manager = rr_env["manager"]
    hook = tmp_path / "timeout.py"
    hook.write_text(
        "import time\n"
        "def bootstrap(session):\n"
        "    time.sleep(30)\n"
        "    session.send(\"printf 'MUST_NOT_APPEAR\\\\n'\")\n",
        encoding="utf-8",
    )
    manager.instances.add("timeout", str(hook))

    with pytest.raises(RemoteRunnerError) as caught:
        manager.create(
            name="timed-bootstrap",
            shell=rr_env["shell"],
            instance_name="timeout",
            bootstrap_timeout=0.2,
        )

    assert caught.value.code == "bootstrap_timed_out"
    state = manager.show(caught.value.context["session_id"])
    assert state["session_status"] == "active"
    assert state["bootstrap_status"] == "timed_out"
    assert b"MUST_NOT_APPEAR" not in manager.tail(state["session_id"]).output


def test_bootstrap_holds_the_writer_lock_for_its_full_run(
    rr_env: Dict[str, Any], tmp_path: Path
) -> None:
    manager = rr_env["manager"]
    store = rr_env["store"]
    marker = tmp_path / "bootstrap-running"
    hook = tmp_path / "exclusive.py"
    hook.write_text(
        "from pathlib import Path\n"
        "import time\n"
        "def bootstrap(session):\n"
        f"    Path({str(marker)!r}).write_text('running')\n"
        "    time.sleep(0.8)\n",
        encoding="utf-8",
    )
    manager.instances.add("exclusive", str(hook))

    with ThreadPoolExecutor(max_workers=1) as executor:
        creating = executor.submit(
            manager.create,
            name="exclusive-bootstrap",
            shell=rr_env["shell"],
            instance_name="exclusive",
            bootstrap_timeout=3,
        )
        deadline = time.monotonic() + 2
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists()
        session_id = store.list_sessions()[0]["session_id"]
        with pytest.raises(StateError) as locked:
            with store.writer_lock(session_id, timeout=0.1):
                pass
        assert locked.value.code == "session_write_locked"
        assert creating.result()["bootstrap_status"] == "succeeded"


def test_bootstrap_launch_failure_finishes_state(
    rr_env: Dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = rr_env["manager"]
    hook = tmp_path / "launch.py"
    hook.write_text("def bootstrap(session):\n    pass\n", encoding="utf-8")
    manager.instances.add("launch", str(hook))

    def fail_to_launch(*args, **kwargs):
        raise OSError("worker unavailable")

    monkeypatch.setattr("remote_runner.session.Popen", fail_to_launch)
    with pytest.raises(RemoteRunnerError) as caught:
        manager.create(
            name="launch-failed",
            shell=rr_env["shell"],
            instance_name="launch",
        )

    assert caught.value.code == "bootstrap_failed"
    state = manager.show(caught.value.context["session_id"])
    assert state["session_status"] == "active"
    assert state["bootstrap_status"] == "failed"
    assert state["bootstrap_ended_at"] is not None
