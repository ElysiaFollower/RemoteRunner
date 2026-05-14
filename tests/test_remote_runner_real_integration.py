"""Opt-in integration tests for Remote Runner against a real SSH machine."""

import json
import os
import posixpath
import shlex
import subprocess
import sys
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("REMOTE_RUNNER_RUN_REAL_TESTS") != "1",
    reason="Set REMOTE_RUNNER_RUN_REAL_TESTS=1 to run real Remote Runner tests",
)


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} is required for real Remote Runner tests")
    return value


def _run_remote_runner(*args: str) -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "remote_runner.cli", *args],
        capture_output=True,
        text=True,
        timeout=60,
    )
    output = result.stdout.strip() or result.stderr.strip()
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"remote-runner returned non-JSON output\n"
            f"args={args!r}\nstdout={result.stdout}\nstderr={result.stderr}"
        ) from exc
    if result.returncode != 0:
        raise AssertionError(f"remote-runner failed: {payload}")
    return payload


def test_real_machine_exec_and_file_transfer_round_trip(tmp_path):
    machine_id = _require_env("REMOTE_RUNNER_REAL_MACHINE")
    remote_cwd = _require_env("REMOTE_RUNNER_REAL_TEST_CWD").rstrip("/")
    probe_id = uuid.uuid4().hex
    probe_name = f"rr_real_integration_{probe_id}.txt"
    remote_path = posixpath.join(remote_cwd, probe_name)
    local_source = tmp_path / probe_name
    local_download = tmp_path / f"downloaded_{probe_name}"
    content = f"remote-runner-real-integration {probe_id}\n"
    local_source.write_text(content)

    session_id = None
    cleanup_done = False
    background_command_id = None
    background_finished = False
    stop_command_id = None
    stop_requested = False
    terminal_id = None
    terminal_destroyed = False
    try:
        doctor = _run_remote_runner("machine", "doctor", machine_id, "--json")
        assert doctor["reachable"] is True
        assert doctor["auth_ok"] is True
        assert doctor["default_cwd_ok"] is True

        session = _run_remote_runner(
            "session",
            "create",
            "--machine",
            machine_id,
            "--cwd",
            remote_cwd,
            "--json",
        )
        session_id = session["session_id"]
        assert session["cwd"] == remote_cwd

        executed = _run_remote_runner(
            "session",
            "exec",
            "--session",
            session_id,
            "--cmd",
            'pwd && printf "remote-runner-real-integration\\n"',
            "--json",
        )
        assert executed["exit_code"] == 0
        assert "remote-runner-real-integration" in executed["stdout"]
        assert "Microsoft Windows" not in executed["stdout"]
        assert "wsl" not in executed["stdout"]

        background = _run_remote_runner(
            "session",
            "exec",
            "--session",
            session_id,
            "--cmd",
            'printf "rr-background-start\\n"; sleep 2; printf "rr-background-end\\n"',
            "--mode",
            "background",
            "--json",
        )
        background_command_id = background["command_id"]
        assert background["status"] == "running"

        import time

        time.sleep(0.5)
        background_show = _run_remote_runner(
            "session",
            "command",
            "show",
            "--session",
            session_id,
            "--command-id",
            background_command_id,
            "--json",
        )
        assert background_show["status"] == "running"
        assert "rr-background-start" in background_show["stdout"]

        background_wait = _run_remote_runner(
            "session",
            "command",
            "wait",
            "--session",
            session_id,
            "--command-id",
            background_command_id,
            "--timeout",
            "5",
            "--json",
        )
        background_finished = background_wait["status"] == "exited"
        assert background_finished is True
        assert background_wait["exit_code"] == 0
        assert "rr-background-end" in background_wait["stdout"]

        stop_background = _run_remote_runner(
            "session",
            "exec",
            "--session",
            session_id,
            "--cmd",
            'printf "rr-stop-start\\n"; sleep 30; printf "rr-stop-end\\n"',
            "--mode",
            "background",
            "--json",
        )
        stop_command_id = stop_background["command_id"]
        assert stop_background["status"] == "running"

        time.sleep(0.5)
        stop_result = _run_remote_runner(
            "session",
            "command",
            "stop",
            "--session",
            session_id,
            "--command-id",
            stop_command_id,
            "--json",
        )
        stop_requested = True
        assert stop_result["status"] == "stopped"
        assert stop_result["exit_code"] == 143
        assert stop_result["stop_requested"] is True
        assert "rr-stop-start" in stop_result["stdout"]

        stop_show = _run_remote_runner(
            "session",
            "command",
            "show",
            "--session",
            session_id,
            "--command-id",
            stop_command_id,
            "--json",
        )
        assert stop_show["status"] == "stopped"
        assert stop_show["exit_code"] == 143

        terminal = _run_remote_runner(
            "terminal",
            "create",
            "--machine",
            machine_id,
            "--cwd",
            remote_cwd,
            "--json",
        )
        terminal_id = terminal["terminal_id"]
        assert terminal["status"] == "active"

        terminal_token = f"rr-terminal-{probe_id}"
        for terminal_input in (
            f"cd {shlex.quote(remote_cwd)}",
            f"export RR_TERMINAL_TOKEN={shlex.quote(terminal_token)}",
            "pwd",
            'printf "$RR_TERMINAL_TOKEN\\n"',
        ):
            sent = _run_remote_runner(
                "terminal",
                "send",
                "--terminal",
                terminal_id,
                "--input",
                terminal_input,
                "--json",
            )
            assert sent["input_sent"] is True

        terminal_read = None
        for _ in range(20):
            terminal_read = _run_remote_runner(
                "terminal",
                "read",
                "--terminal",
                terminal_id,
                "--json",
            )
            if terminal_token in terminal_read["transcript"]:
                break
            time.sleep(0.2)
        assert terminal_read is not None
        assert remote_cwd in terminal_read["transcript"]
        assert terminal_token in terminal_read["transcript"]

        terminal_destroy = _run_remote_runner(
            "terminal",
            "destroy",
            "--terminal",
            terminal_id,
            "--json",
        )
        terminal_destroyed = terminal_destroy["status"] == "destroyed"
        assert terminal_destroyed is True

        put = _run_remote_runner(
            "file",
            "put",
            "--session",
            session_id,
            "--local",
            str(local_source),
            "--remote",
            remote_path,
            "--json",
        )
        assert put["status"] == "completed"
        assert put["destination"] == remote_path

        listing = _run_remote_runner(
            "file",
            "list",
            "--session",
            session_id,
            "--remote",
            remote_cwd,
            "--json",
        )
        assert any(entry["name"] == probe_name for entry in listing["entries"])

        get = _run_remote_runner(
            "file",
            "get",
            "--session",
            session_id,
            "--remote",
            remote_path,
            "--local",
            str(local_download),
            "--json",
        )
        assert get["status"] == "completed"
        assert local_download.read_text() == content

        cleanup = _run_remote_runner(
            "session",
            "exec",
            "--session",
            session_id,
            "--cmd",
            (
                f"rm -f {shlex.quote(probe_name)} && "
                f"rm -rf .remote-runner/commands/{shlex.quote(background_command_id or '')} && "
                f"rm -rf .remote-runner/commands/{shlex.quote(stop_command_id or '')} && "
                f"test ! -e {shlex.quote(probe_name)}"
            ),
            "--json",
        )
        cleanup_done = cleanup["exit_code"] == 0
        assert cleanup_done is True
    finally:
        if session_id and background_command_id and not background_finished:
            _run_remote_runner(
                "session",
                "command",
                "stop",
                "--session",
                session_id,
                "--command-id",
                background_command_id,
                "--json",
            )
        if session_id and stop_command_id and not stop_requested:
            _run_remote_runner(
                "session",
                "command",
                "stop",
                "--session",
                session_id,
                "--command-id",
                stop_command_id,
                "--json",
            )
        if terminal_id and not terminal_destroyed:
            _run_remote_runner(
                "terminal",
                "destroy",
                "--terminal",
                terminal_id,
                "--json",
            )
        if session_id and not cleanup_done:
            _run_remote_runner(
                "session",
                "exec",
                "--session",
                session_id,
                "--cmd",
                (
                    f"rm -f {shlex.quote(probe_name)} && "
                    f"rm -rf .remote-runner/commands/{shlex.quote(background_command_id or '')} && "
                    f"rm -rf .remote-runner/commands/{shlex.quote(stop_command_id or '')}"
                ),
                "--json",
            )
        if session_id:
            _run_remote_runner("session", "destroy", "--session", session_id, "--json")
