import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any, Callable, Dict
import uuid

import pytest

from remote_runner.session import SessionManager
from remote_runner.state import StateStore
from remote_runner.tmux import TmuxTerminal


@pytest.fixture
def rr_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Dict[str, Any]:
    tmux = shutil.which("tmux")
    if tmux is None:
        pytest.skip("tmux is required")
    socket_name = f"rr_test_{uuid.uuid4().hex}"
    state_dir = tmp_path / "state"
    monkeypatch.setenv("REMOTE_RUNNER_STATE_DIR", str(state_dir))
    monkeypatch.setenv("REMOTE_RUNNER_TMUX_SOCKET", socket_name)
    monkeypatch.setenv("REMOTE_RUNNER_TMUX_BINARY", tmux)

    shell = tmp_path / "test-shell"
    shell.write_text(
        "#!/bin/sh\n"
        "printf 'RR_INITIAL_OUTPUT\\n'\n"
        "PS1='RR_TEST> '\n"
        "export PS1\n"
        "exec /bin/sh -i\n",
        encoding="utf-8",
    )
    shell.chmod(0o700)

    terminal = TmuxTerminal(binary=tmux, socket_name=socket_name)
    store = StateStore(state_dir)
    manager = SessionManager(store=store, terminal=terminal)
    try:
        yield {
            "manager": manager,
            "store": store,
            "terminal": terminal,
            "shell": str(shell),
            "state_dir": state_dir,
            "socket_name": socket_name,
            "tmux": tmux,
        }
    finally:
        subprocess.run(
            [tmux, "-L", socket_name, "kill-server"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


@pytest.fixture
def wait_for_output() -> Callable[..., bytes]:
    def wait(
        manager: SessionManager,
        session_ref: str,
        expected: bytes,
        *,
        timeout: float = 5.0,
    ) -> bytes:
        deadline = time.monotonic() + timeout
        latest = b""
        while time.monotonic() < deadline:
            latest = manager.tail(session_ref, max_bytes=65536).output
            if expected in latest:
                return latest
            time.sleep(0.02)
        pytest.fail(f"timed out waiting for {expected!r}; latest={latest!r}")

    return wait


@pytest.fixture
def cli_env(rr_env: Dict[str, Any]) -> Dict[str, str]:
    environment = os.environ.copy()
    environment["REMOTE_RUNNER_STATE_DIR"] = str(rr_env["state_dir"])
    environment["REMOTE_RUNNER_TMUX_SOCKET"] = rr_env["socket_name"]
    environment["REMOTE_RUNNER_TMUX_BINARY"] = rr_env["tmux"]
    return environment
