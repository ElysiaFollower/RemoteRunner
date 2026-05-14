"""Tests for the mount-free Remote Runner MVP core."""

import io
import json
import os
import stat
import sys
import threading
from pathlib import Path

import pytest

from remote_runner import utils as runner_utils
from remote_runner.cli import main as remote_cli_main
from remote_runner.remote_backend import ParamikoRemoteBackend, RemoteCommandResult
from remote_runner.remote_file import RemoteFileManager
from remote_runner.remote_machine import RemoteMachineManager
from remote_runner.remote_run import RemoteRunManager
from remote_runner.remote_session import RemoteSessionManager
from remote_runner.remote_state import (
    get_machines_file,
    load_artifact_manifest,
    load_machines_state,
    load_run_state,
    load_session_state,
    load_transfer_records,
)


class FakeBackend:
    """Fake remote backend for manager tests."""

    def __init__(self):
        self.commands = []
        self.background_commands = {}
        self.puts = []
        self.gets = []
        self.lists = []
        self.terminals = {}
        self.block_started = threading.Event()
        self.block_release = threading.Event()

    def doctor(self, machine):
        return {
            "machine_id": machine.machine_id,
            "reachable": True,
            "auth_ok": True,
            "default_cwd_ok": True,
            "checked_at": "2026-05-08T00:00:00Z",
            "errors": [],
        }

    def run(self, machine, cwd, command, timeout=300):
        self.commands.append(
            {
                "machine_id": machine.machine_id,
                "cwd": cwd,
                "command": command,
                "timeout": timeout,
            }
        )
        if command == "block":
            self.block_started.set()
            assert self.block_release.wait(timeout=2)
        if command == "backend-error":
            raise RuntimeError("ssh failed")
        if command == "exit-seven":
            return RemoteCommandResult(
                stdout="",
                stderr="failed\n",
                exit_code=7,
                started_at="2026-05-08T00:00:01Z",
                ended_at="2026-05-08T00:00:02Z",
                duration_ms=1000,
            )
        return RemoteCommandResult(
            stdout=f"ran {command}\n",
            stderr="",
            exit_code=0,
            started_at="2026-05-08T00:00:01Z",
            ended_at="2026-05-08T00:00:02Z",
            duration_ms=1000,
        )

    def start_background(self, machine, cwd, command, command_id, timeout=15):
        self.background_commands[command_id] = {
            "machine_id": machine.machine_id,
            "cwd": cwd,
            "command": command,
            "status": "running",
            "exit_code": None,
            "stdout": "started\n",
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
            "ended_at": None,
            "remote_pid": "12345",
        }
        return {
            "remote_state_dir": f"{cwd}/.remote-runner/commands/{command_id}",
            "remote_stdout_file": f"{cwd}/.remote-runner/commands/{command_id}/stdout.log",
            "remote_stderr_file": f"{cwd}/.remote-runner/commands/{command_id}/stderr.log",
            "remote_status_file": f"{cwd}/.remote-runner/commands/{command_id}/status",
            "remote_pid_file": f"{cwd}/.remote-runner/commands/{command_id}/pid",
            "remote_exit_code_file": f"{cwd}/.remote-runner/commands/{command_id}/exit_code",
            "remote_ended_at_file": f"{cwd}/.remote-runner/commands/{command_id}/ended_at",
            "remote_pid": "12345",
        }

    def inspect_background(self, machine, command_record, stdout_limit=8192, stderr_limit=8192):
        record = self.background_commands[command_record["command_id"]]
        stdout = record["stdout"]
        stderr = record["stderr"]
        return {
            "status": record["status"],
            "exit_code": record["exit_code"],
            "stdout": stdout[:stdout_limit],
            "stderr": stderr[:stderr_limit],
            "stdout_truncated": len(stdout) > stdout_limit,
            "stderr_truncated": len(stderr) > stderr_limit,
            "ended_at": record["ended_at"],
        }

    def stop_background(self, machine, command_record):
        record = self.background_commands[command_record["command_id"]]
        record["status"] = "stopped"
        record["exit_code"] = 143
        record["ended_at"] = "2026-05-08T00:00:05Z"
        return {"stop_result": "stopped"}

    def finish_background(self, command_id, exit_code=0, stdout="done\n", stderr=""):
        record = self.background_commands[command_id]
        record["status"] = "exited"
        record["exit_code"] = exit_code
        record["stdout"] = stdout
        record["stderr"] = stderr
        record["ended_at"] = "2026-05-08T00:00:04Z"

    def create_terminal(self, machine, cwd, terminal_id, width=120, height=40, history_limit=10000):
        self.terminals[terminal_id] = {
            "machine_id": machine.machine_id,
            "cwd": cwd,
            "env": {},
            "status": "active",
            "transcript": f"$ cd {cwd}\n",
            "remote_terminal_name": f"rr_{terminal_id}",
        }
        return {
            "backend": "tmux",
            "remote_terminal_name": f"rr_{terminal_id}",
            "history_limit": history_limit,
            "width": width,
            "height": height,
        }

    def send_terminal_input(self, machine, terminal_record, input_text, enter=True):
        terminal_id = terminal_record.get("terminal_id") or terminal_record["session_id"]
        terminal = self.terminals[terminal_id]
        terminal["transcript"] += f"$ {input_text}\n"
        if input_text.startswith("cd "):
            path = input_text.split(" ", 1)[1].strip()
            terminal["cwd"] = path
        elif input_text.startswith("export "):
            key, value = input_text[len("export ") :].split("=", 1)
            terminal["env"][key] = value
        elif input_text == "pwd":
            terminal["transcript"] += f"{terminal['cwd']}\n"
        elif input_text == 'printf "$RR_TOKEN\\n"':
            terminal["transcript"] += f"{terminal['env'].get('RR_TOKEN', '')}\n"
        elif input_text.startswith("echo "):
            terminal["transcript"] += input_text[len("echo ") :] + "\n"
        return {"input_sent": True}

    def capture_terminal(self, machine, terminal_record):
        terminal_id = terminal_record.get("terminal_id") or terminal_record["session_id"]
        terminal = self.terminals[terminal_id]
        return {"status": terminal["status"], "transcript": terminal["transcript"]}

    def destroy_terminal(self, machine, terminal_record):
        terminal_id = terminal_record.get("terminal_id") or terminal_record["session_id"]
        terminal = self.terminals[terminal_id]
        terminal["status"] = "destroyed"
        return {"destroy_result": "destroyed"}

    def start_session_command(
        self,
        machine,
        session_record,
        command,
        command_id,
        cwd=None,
        cwd_override=False,
    ):
        terminal = self.terminals[session_record["session_id"]]
        self.commands.append(
            {
                "machine_id": machine.machine_id,
                "cwd": cwd or session_record["cwd"],
                "command": command,
                "timeout": None,
                "cwd_override": cwd_override,
            }
        )
        if command == "backend-error":
            raise RuntimeError("ssh failed")
        if command == "block":
            self.block_started.set()
            assert self.block_release.wait(timeout=2)

        stdout, stderr, exit_code = self._execute_terminal_command(terminal, command, cwd, cwd_override)
        status = "running" if command in {"sleep 30", "tail -f app.log"} else "exited"
        if command in {"sleep 30", "tail -f app.log"}:
            stdout = "started\n"
            stderr = ""
            exit_code = None
        self.background_commands[command_id] = {
            "machine_id": machine.machine_id,
            "cwd": cwd or session_record["cwd"],
            "command": command,
            "status": status,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": False,
            "stderr_truncated": False,
            "started_at": "2026-05-08T00:00:01Z",
            "ended_at": None if status == "running" else "2026-05-08T00:00:02Z",
        }
        remote_state_dir = f"{session_record['cwd']}/.remote-runner/commands/{command_id}"
        return {
            "command_backend": "tmux",
            "remote_state_dir": remote_state_dir,
            "remote_stdout_file": f"{remote_state_dir}/stdout.log",
            "remote_stderr_file": f"{remote_state_dir}/stderr.log",
            "remote_status_file": f"{remote_state_dir}/status",
            "remote_exit_code_file": f"{remote_state_dir}/exit_code",
            "remote_started_at_file": f"{remote_state_dir}/started_at",
            "remote_ended_at_file": f"{remote_state_dir}/ended_at",
            "remote_wrapper_file": f"{remote_state_dir}/run.sh",
        }

    def wait_session_command(self, machine, command_record, timeout=300, stdout_limit=8192, stderr_limit=8192):
        self.commands[-1]["timeout"] = timeout
        return self.inspect_session_command(
            machine,
            command_record,
            stdout_limit=stdout_limit,
            stderr_limit=stderr_limit,
        )

    def inspect_session_command(self, machine, command_record, stdout_limit=8192, stderr_limit=8192):
        record = self.background_commands[command_record["command_id"]]
        stdout = record["stdout"]
        stderr = record["stderr"]
        return {
            "status": record["status"],
            "exit_code": record["exit_code"],
            "stdout": stdout[:stdout_limit],
            "stderr": stderr[:stderr_limit],
            "stdout_truncated": len(stdout) > stdout_limit,
            "stderr_truncated": len(stderr) > stderr_limit,
            "started_at": record["started_at"],
            "ended_at": record["ended_at"],
        }

    def stop_session_command(self, machine, session_record, command_record):
        record = self.background_commands[command_record["command_id"]]
        record["status"] = "stopped"
        record["exit_code"] = 143
        record["ended_at"] = "2026-05-08T00:00:05Z"
        return {"stop_result": "stopped"}

    def _execute_terminal_command(self, terminal, command, cwd=None, cwd_override=False):
        if cwd_override and cwd:
            terminal["cwd"] = cwd
        terminal["transcript"] += f"$ {command}\n"
        if command.startswith("cd "):
            path = command.split(" ", 1)[1].strip()
            terminal["cwd"] = path
            return "", "", 0
        if command.startswith("export "):
            key, value = command[len("export ") :].split("=", 1)
            terminal["env"][key] = value
            return "", "", 0
        if command == "pwd":
            stdout = f"{terminal['cwd']}\n"
            terminal["transcript"] += stdout
            return stdout, "", 0
        if command == 'printf "$RR_TOKEN\\n"':
            stdout = f"{terminal['env'].get('RR_TOKEN', '')}\n"
            terminal["transcript"] += stdout
            return stdout, "", 0
        if command.startswith("echo "):
            stdout = command[len("echo ") :] + "\n"
            terminal["transcript"] += stdout
            return stdout, "", 0
        if command == "exit-seven":
            terminal["transcript"] += "failed\n"
            return "", "failed\n", 7
        return f"ran {command}\n", "", 0

    def put(self, machine, local_path, remote_path):
        self.puts.append((machine.machine_id, local_path, remote_path))
        if "missing" in local_path:
            raise FileNotFoundError(local_path)
        return {"size_bytes": 12, "sha256": "abc123"}

    def get(self, machine, remote_path, local_path):
        self.gets.append((machine.machine_id, remote_path, local_path))
        if "denied" in remote_path:
            raise PermissionError(remote_path)
        return {"size_bytes": 34, "sha256": "def456"}

    def list(self, machine, remote_path):
        self.lists.append((machine.machine_id, remote_path))
        if "gone" in remote_path:
            raise FileNotFoundError(remote_path)
        return {
            "entries": [
                {
                    "name": "result.txt",
                    "path": f"{remote_path}/result.txt",
                    "type": "file",
                    "size_bytes": 34,
                    "mtime": 1778198400,
                }
            ]
        }


@pytest.fixture
def remote_state_dir(tmp_path, monkeypatch):
    state_dir = tmp_path / "remote-state"
    monkeypatch.setenv("REMOTE_RUNNER_STATE_DIR", str(state_dir))
    return state_dir


def _write_key(tmp_path: Path) -> Path:
    key_path = tmp_path / "id_test"
    key_path.write_text("test-key")
    return key_path


def _add_key_machine(machine_manager: RemoteMachineManager, tmp_path: Path):
    return machine_manager.add(
        machine_id="lab-gpu-01",
        host="127.0.0.1",
        port=2222,
        user="ely",
        auth_type="key",
        key_path=str(_write_key(tmp_path)),
        default_cwd="/home/ely/project",
    )


def test_seed_runner_remote_cli_wrapper_points_to_remote_runner_entrypoint():
    from seed_runner.remote_cli import main as legacy_main

    assert legacy_main is remote_cli_main


def test_remote_runner_modules_own_target_implementation():
    assert remote_cli_main.__module__ == "remote_runner.cli"
    assert ParamikoRemoteBackend.__module__ == "remote_runner.remote_backend"
    assert RemoteFileManager.__module__ == "remote_runner.remote_file"
    assert RemoteMachineManager.__module__ == "remote_runner.remote_machine"
    assert RemoteRunManager.__module__ == "remote_runner.remote_run"
    assert RemoteSessionManager.__module__ == "remote_runner.remote_session"
    assert load_run_state.__module__ == "remote_runner.remote_state"


def test_seed_runner_remote_wrappers_reexport_target_implementation():
    from remote_runner.remote_backend import ParamikoRemoteBackend as TargetBackend
    from remote_runner.remote_file import RemoteFileManager as TargetFileManager
    from remote_runner.remote_machine import RemoteMachineManager as TargetMachineManager
    from remote_runner.remote_run import RemoteRunManager as TargetRunManager
    from remote_runner.remote_session import RemoteSessionManager as TargetSessionManager
    from remote_runner.remote_state import load_run_state as target_load_run_state
    from seed_runner.remote_backend import ParamikoRemoteBackend as LegacyBackend
    from seed_runner.remote_file import RemoteFileManager as LegacyFileManager
    from seed_runner.remote_machine import RemoteMachineManager as LegacyMachineManager
    from seed_runner.remote_run import RemoteRunManager as LegacyRunManager
    from seed_runner.remote_session import RemoteSessionManager as LegacySessionManager
    from seed_runner.remote_state import load_run_state as legacy_load_run_state

    assert LegacyBackend is TargetBackend
    assert LegacyMachineManager is TargetMachineManager
    assert LegacySessionManager is TargetSessionManager
    assert LegacyFileManager is TargetFileManager
    assert LegacyRunManager is TargetRunManager
    assert legacy_load_run_state is target_load_run_state


def test_seed_runner_utils_wrapper_reexports_target_helpers():
    from seed_runner import utils as legacy_utils

    assert legacy_utils.get_timestamp is runner_utils.get_timestamp
    assert legacy_utils.generate_id is runner_utils.generate_id


def test_generate_id_stays_unique_when_timestamp_collides(monkeypatch):
    class FixedNow:
        def strftime(self, fmt):
            return "20260511_121146_968174"

    class FixedDatetime:
        @staticmethod
        def now(tz=None):
            return FixedNow()

    monkeypatch.setattr(runner_utils, "datetime", FixedDatetime)

    assert runner_utils.generate_id("xfer") != runner_utils.generate_id("xfer")


def test_get_timestamp_uses_utc_z_suffix():
    timestamp = runner_utils.get_timestamp()

    assert timestamp.endswith("Z")
    assert "+00:00" not in timestamp


def test_machine_registry_redacts_credentials_and_recovers(remote_state_dir, tmp_path):
    machine_manager = RemoteMachineManager()
    key_machine = _add_key_machine(machine_manager, tmp_path)
    password_machine = machine_manager.add(
        machine_id="ops-01",
        host="example.internal",
        port=22,
        user="deploy",
        auth_type="password",
        password="secret-password",
        default_cwd="/srv/app",
    )

    assert key_machine["machine_id"] == "lab-gpu-01"
    assert password_machine["password"] == "***REDACTED***"

    reloaded_manager = RemoteMachineManager()
    machines = reloaded_manager.list()
    assert machines["summary"] == {"machine_count": 2}
    assert all(machine.get("password") != "secret-password" for machine in machines["machines"])
    assert reloaded_manager.show("ops-01")["password"] == "***REDACTED***"

    doctor = reloaded_manager.doctor("lab-gpu-01", FakeBackend())
    assert doctor["reachable"] is True
    assert doctor["auth_ok"] is True
    assert doctor["default_cwd_ok"] is True

    removed = reloaded_manager.remove("ops-01")
    assert removed == {"machine_id": "ops-01", "removed": True}
    assert reloaded_manager.list()["summary"] == {"machine_count": 1}
    assert oct(os.stat(get_machines_file()).st_mode & 0o777) == "0o600"


def test_session_exec_logs_state_and_preserves_nonzero_exit(remote_state_dir, tmp_path):
    machine_manager = RemoteMachineManager()
    _add_key_machine(machine_manager, tmp_path)
    backend = FakeBackend()
    session_manager = RemoteSessionManager(machine_manager=machine_manager, backend=backend)

    created = session_manager.create("lab-gpu-01")
    session_id = created["session_id"]
    assert created["cwd"] == "/home/ely/project"
    assert created["busy"] is False
    assert Path(created["log_dir_local"]).is_dir()

    reloaded_manager = RemoteSessionManager(
        machine_manager=RemoteMachineManager(),
        backend=backend,
    )
    result = reloaded_manager.exec(session_id, "echo ok", timeout=123)
    assert result["exit_code"] == 0
    assert result["stdout"] == "ok\n"
    assert result["duration_ms"] == 1000
    assert Path(result["log_file_local"]).read_text().find("ok") >= 0
    assert backend.commands[-1]["timeout"] == 123

    nonzero = reloaded_manager.exec(session_id, "exit-seven")
    assert nonzero["exit_code"] == 7
    assert nonzero["stderr"] == "failed\n"

    shown = reloaded_manager.show(session_id)
    assert shown["status"] == "active"
    assert shown["busy"] is False
    assert shown["last_command"] == "exit-seven"
    assert shown["last_exit_code"] == 7
    assert shown["command_count"] == 2
    assert len(shown["commands"]) == 2

    logs = reloaded_manager.logs(session_id)
    assert [log["index"] for log in logs["logs"]] == [1, 2]
    assert all(Path(log["log_file_local"]).exists() for log in logs["logs"])

    destroyed = reloaded_manager.destroy(session_id)
    assert destroyed["status"] == "destroyed"
    assert destroyed["logs_preserved"] is True
    with pytest.raises(RuntimeError, match="destroyed"):
        reloaded_manager.exec(session_id, "echo after destroy")


def test_session_exec_records_backend_errors_and_clears_busy(remote_state_dir, tmp_path):
    machine_manager = RemoteMachineManager()
    _add_key_machine(machine_manager, tmp_path)
    backend = FakeBackend()
    session_manager = RemoteSessionManager(machine_manager=machine_manager, backend=backend)
    session_id = session_manager.create("lab-gpu-01")["session_id"]

    with pytest.raises(RuntimeError, match="ssh failed"):
        session_manager.exec(session_id, "backend-error")

    session = session_manager.show(session_id)
    assert session["busy"] is False
    assert session["command_count"] == 1
    assert session["commands"][0]["status"] == "failed"
    assert session["commands"][0]["error"] == "ssh failed"
    assert Path(session["commands"][0]["log_file_local"]).read_text().find("ssh failed") >= 0


def test_session_exec_rejects_concurrent_commands(remote_state_dir, tmp_path):
    machine_manager = RemoteMachineManager()
    _add_key_machine(machine_manager, tmp_path)
    backend = FakeBackend()
    session_manager = RemoteSessionManager(machine_manager=machine_manager, backend=backend)
    session_id = session_manager.create("lab-gpu-01")["session_id"]
    result = {}

    def run_blocking_command():
        result["first"] = session_manager.exec(session_id, "block")

    worker = threading.Thread(target=run_blocking_command)
    worker.start()
    assert backend.block_started.wait(timeout=2)

    try:
        with pytest.raises(RuntimeError, match="busy"):
            session_manager.exec(session_id, "echo second")
    finally:
        backend.block_release.set()
        worker.join(timeout=2)

    assert not worker.is_alive()
    assert result["first"]["exit_code"] == 0
    assert session_manager.show(session_id)["command_count"] == 1
    assert load_session_state(session_id)["busy"] is False


def test_session_background_command_can_be_polled_waited_and_stopped(remote_state_dir, tmp_path):
    machine_manager = RemoteMachineManager()
    _add_key_machine(machine_manager, tmp_path)
    backend = FakeBackend()
    session_manager = RemoteSessionManager(machine_manager=machine_manager, backend=backend)
    session_id = session_manager.create("lab-gpu-01")["session_id"]

    started = session_manager.exec(session_id, "sleep 30", mode="background")
    command_id = started["command_id"]

    assert started["status"] == "running"
    assert started["mode"] == "background"
    assert started["exit_code"] is None
    assert started["remote_state_dir"].endswith(f"/.remote-runner/commands/{command_id}")
    assert started["remote_stdout_file"].endswith(f"/.remote-runner/commands/{command_id}/stdout.log")
    assert started["remote_status_file"].endswith(f"/.remote-runner/commands/{command_id}/status")
    assert session_manager.show(session_id)["busy"] is False
    assert session_manager.show(session_id)["command_count"] == 1

    running = RemoteSessionManager(
        machine_manager=RemoteMachineManager(),
        backend=backend,
    ).command_show(session_id, command_id)
    assert running["status"] == "running"
    assert running["stdout"] == "started\n"
    assert running["stdout_truncated"] is False

    timed_out = session_manager.command_wait(session_id, command_id, timeout=0)
    assert timed_out["status"] == "running"
    assert timed_out["wait_timed_out"] is True

    backend.finish_background(
        command_id,
        exit_code=7,
        stdout="x" * 20,
        stderr="failed\n",
    )
    finished = session_manager.command_show(
        session_id,
        command_id,
        stdout_limit=5,
        stderr_limit=20,
    )
    assert finished["status"] == "exited"
    assert finished["exit_code"] == 7
    assert finished["stdout"] == "xxxxx"
    assert finished["stdout_truncated"] is True
    assert finished["stderr"] == "failed\n"
    assert Path(finished["log_file_local"]).read_text().find("[stdout_truncated] true") >= 0
    refreshed = session_manager.command_show(
        session_id,
        command_id,
        stdout_limit=30,
        stderr_limit=20,
    )
    assert refreshed["stdout"] == "x" * 20
    assert refreshed["stdout_truncated"] is False
    assert session_manager.command_list(session_id)["summary"]["command_count"] == 1


def test_session_background_command_stop_blocks_destroy_until_stopped(remote_state_dir, tmp_path):
    machine_manager = RemoteMachineManager()
    _add_key_machine(machine_manager, tmp_path)
    backend = FakeBackend()
    session_manager = RemoteSessionManager(machine_manager=machine_manager, backend=backend)
    session_id = session_manager.create("lab-gpu-01")["session_id"]
    command_id = session_manager.exec(session_id, "tail -f app.log", mode="background")[
        "command_id"
    ]

    with pytest.raises(RuntimeError, match="running background commands"):
        session_manager.destroy(session_id)

    stopped = session_manager.command_stop(session_id, command_id)

    assert stopped["status"] == "stopped"
    assert stopped["exit_code"] == 143
    assert stopped["stop_requested"] is True
    assert stopped["stop_result"] == "stopped"
    assert session_manager.destroy(session_id)["status"] == "destroyed"


def test_remote_runner_cli_background_command_outputs_json(remote_state_dir, tmp_path, monkeypatch, capsys):
    machine_manager = RemoteMachineManager()
    _add_key_machine(machine_manager, tmp_path)
    backend = FakeBackend()
    manager = RemoteSessionManager(machine_manager=machine_manager, backend=backend)
    session_id = manager.create("lab-gpu-01")["session_id"]
    monkeypatch.setattr("remote_runner.cli.get_remote_session_manager", lambda: manager)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "remote-runner",
            "session",
            "exec",
            "--session",
            session_id,
            "--cmd",
            "sleep 30",
            "--mode",
            "background",
            "--json",
        ],
    )

    remote_cli_main()
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "running"
    assert payload["mode"] == "background"
    assert payload["command_id"].startswith("cmd_")
    assert payload["remote_stdout_file"].endswith("/stdout.log")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "remote-runner",
            "session",
            "command",
            "result",
            "--session",
            session_id,
            "--command-id",
            payload["command_id"],
            "--json",
        ],
    )

    remote_cli_main()
    result_payload = json.loads(capsys.readouterr().out)

    assert result_payload["status"] == "running"
    assert result_payload["command_id"] == payload["command_id"]
    assert result_payload["remote_status_file"].endswith("/status")


def test_session_preserves_shell_state_and_incremental_transcript(
    remote_state_dir,
    tmp_path,
):
    machine_manager = RemoteMachineManager()
    _add_key_machine(machine_manager, tmp_path)
    backend = FakeBackend()
    session_manager = RemoteSessionManager(machine_manager=machine_manager, backend=backend)

    created = session_manager.create("lab-gpu-01", cwd="/home/ely/project")
    session_id = created["session_id"]

    assert created["status"] == "active"
    assert created["backend"] == "tmux"
    assert created["remote_backend_name"].startswith("rr_sess_")
    assert Path(created["transcript_file_local"]).exists()

    reloaded = RemoteSessionManager(machine_manager=RemoteMachineManager(), backend=backend)
    reloaded.exec(session_id, "cd /home/ely/project/subdir")
    reloaded.exec(session_id, "export RR_TOKEN=terminal-ok")
    pwd = reloaded.exec(session_id, "pwd")
    token = reloaded.exec(session_id, 'printf "$RR_TOKEN\\n"')

    assert pwd["stdout"] == "/home/ely/project/subdir\n"
    assert token["stdout"] == "terminal-ok\n"

    transcript = reloaded.read(session_id)
    cursor = transcript["cursor"]

    assert "/home/ely/project/subdir" in transcript["transcript"]
    assert "terminal-ok" in transcript["transcript"]
    assert load_session_state(session_id)["transcript_cursor"] == cursor
    assert Path(transcript["transcript_file_local"]).read_text().find("terminal-ok") >= 0

    reloaded.send(session_id, "echo after-cursor")
    incremental = reloaded.read(session_id, since=cursor)

    assert "after-cursor" in incremental["transcript"]
    assert incremental["since"] == cursor
    assert incremental["cursor"] > cursor

    destroyed = reloaded.destroy(session_id)
    assert destroyed["status"] == "destroyed"
    assert destroyed["destroy_result"] == "destroyed"
    destroyed_read = reloaded.read(session_id)
    assert "terminal-ok" in destroyed_read["transcript"]
    assert destroyed_read["status"] == "destroyed"
    with pytest.raises(RuntimeError, match="not active"):
        reloaded.send(session_id, "pwd")


def test_session_read_appends_rotated_remote_transcript(
    remote_state_dir,
    tmp_path,
):
    machine_manager = RemoteMachineManager()
    _add_key_machine(machine_manager, tmp_path)
    backend = FakeBackend()
    session_manager = RemoteSessionManager(machine_manager=machine_manager, backend=backend)

    created = session_manager.create("lab-gpu-01", cwd="/home/ely/project")
    session_id = created["session_id"]
    transcript_file = Path(created["transcript_file_local"])

    backend.terminals[session_id]["transcript"] = "line-1\nline-2\nline-3\n"
    first_read = session_manager.read(session_id)

    backend.terminals[session_id]["transcript"] = "line-3\nline-4\n"
    second_read = session_manager.read(session_id, since=first_read["cursor"])

    assert second_read["transcript"] == "line-4\n"
    assert second_read["cursor"] > first_read["cursor"]
    assert transcript_file.read_text() == "line-1\nline-2\nline-3\nline-4\n"


def test_remote_runner_cli_session_send_read_outputs_json(
    remote_state_dir,
    tmp_path,
    monkeypatch,
    capsys,
):
    machine_manager = RemoteMachineManager()
    _add_key_machine(machine_manager, tmp_path)
    backend = FakeBackend()
    manager = RemoteSessionManager(machine_manager=machine_manager, backend=backend)
    monkeypatch.setattr("remote_runner.cli.get_remote_session_manager", lambda: manager)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "remote-runner",
            "session",
            "create",
            "--machine",
            "lab-gpu-01",
            "--cwd",
            "/home/ely/project",
            "--json",
        ],
    )

    remote_cli_main()
    created = json.loads(capsys.readouterr().out)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "remote-runner",
            "session",
            "send",
            "--session",
            created["session_id"],
            "--input",
            "pwd",
            "--json",
        ],
    )
    remote_cli_main()
    sent = json.loads(capsys.readouterr().out)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "remote-runner",
            "session",
            "read",
            "--session",
            created["session_id"],
            "--json",
        ],
    )
    remote_cli_main()
    read = json.loads(capsys.readouterr().out)

    assert created["session_id"].startswith("sess_")
    assert sent["input_sent"] is True
    assert "/home/ely/project" in read["transcript"]


def test_file_transfer_records_success_and_failure(remote_state_dir, tmp_path):
    machine_manager = RemoteMachineManager()
    _add_key_machine(machine_manager, tmp_path)
    backend = FakeBackend()
    session_manager = RemoteSessionManager(machine_manager=machine_manager, backend=backend)
    session_id = session_manager.create("lab-gpu-01")["session_id"]
    file_manager = RemoteFileManager(machine_manager=machine_manager, backend=backend)

    put = file_manager.put(session_id, "/local/input.txt", "/remote/input.txt")
    get = file_manager.get(session_id, "/remote/result.txt", "/local/result.txt")
    listing = file_manager.list(session_id, "/remote")

    assert put["direction"] == "put"
    assert put["size_bytes"] == 12
    assert get["direction"] == "get"
    assert get["sha256"] == "def456"
    assert listing["direction"] == "list"
    assert listing["entries"][0]["name"] == "result.txt"

    with pytest.raises(RuntimeError, match="missing-input"):
        file_manager.put(session_id, "/local/missing-input.txt", "/remote/input.txt")
    with pytest.raises(RuntimeError, match="denied"):
        file_manager.get(session_id, "/remote/denied.txt", "/local/result.txt")
    with pytest.raises(RuntimeError, match="gone"):
        file_manager.list(session_id, "/remote/gone")

    records = load_transfer_records(session_id)
    artifacts = load_artifact_manifest(session_id)
    assert [record["direction"] for record in records] == [
        "put",
        "get",
        "list",
        "put",
        "get",
        "list",
    ]
    assert [record["status"] for record in records] == [
        "completed",
        "completed",
        "completed",
        "failed",
        "failed",
        "failed",
    ]
    assert records[-1]["error"] == "/remote/gone"
    assert artifacts["artifacts"] == [
        {
            "artifact_id": get["transfer_id"],
            "transfer_id": get["transfer_id"],
            "source_remote": "/remote/result.txt",
            "local_path": "/local/result.txt",
            "recorded_at": get["ended_at"],
            "size_bytes": 34,
            "sha256": "def456",
        }
    ]
    assert load_session_state(session_id)["transfer_count"] == 6


def test_run_once_records_closed_loop_manifest(remote_state_dir, tmp_path):
    machine_manager = RemoteMachineManager()
    _add_key_machine(machine_manager, tmp_path)
    backend = FakeBackend()
    session_manager = RemoteSessionManager(machine_manager=machine_manager, backend=backend)
    file_manager = RemoteFileManager(
        machine_manager=machine_manager,
        session_manager=session_manager,
        backend=backend,
    )
    run_manager = RemoteRunManager(
        session_manager=session_manager,
        file_manager=file_manager,
    )

    run = run_manager.once(
        machine_id="lab-gpu-01",
        cwd="/home/ely/project",
        command="python train.py",
        inputs=[
            {
                "local_path": "/local/input.json",
                "remote_path": "/home/ely/project/input.json",
            }
        ],
        artifacts=[
            {
                "remote_path": "/home/ely/project/output.txt",
                "local_path": "/local/output.txt",
            }
        ],
        timeout=77,
    )

    assert run["status"] == "succeeded"
    assert run["machine_id"] == "lab-gpu-01"
    assert run["cwd"] == "/home/ely/project"
    assert run["command_result"]["exit_code"] == 0
    assert run["inputs"][0]["status"] == "completed"
    assert run["artifacts"][0]["status"] == "completed"
    assert run["destroy_session_result"]["status"] == "destroyed"
    assert backend.puts[-1] == (
        "lab-gpu-01",
        "/local/input.json",
        "/home/ely/project/input.json",
    )
    assert backend.commands[-1]["command"] == "python train.py"
    assert backend.commands[-1]["timeout"] == 77
    assert backend.gets[-1] == (
        "lab-gpu-01",
        "/home/ely/project/output.txt",
        "/local/output.txt",
    )
    assert load_session_state(run["session_id"])["status"] == "destroyed"
    assert load_run_state(run["run_id"])["run_id"] == run["run_id"]

    listed = run_manager.list()
    assert listed["summary"] == {"run_count": 1}
    assert listed["runs"][0]["run_id"] == run["run_id"]
    assert listed["runs"][0]["exit_code"] == 0
    assert run_manager.show(run["run_id"])["artifacts"][0]["local_path"] == "/local/output.txt"


def test_run_once_marks_nonzero_exit_failed_and_destroys_session(remote_state_dir, tmp_path):
    machine_manager = RemoteMachineManager()
    _add_key_machine(machine_manager, tmp_path)
    backend = FakeBackend()
    session_manager = RemoteSessionManager(machine_manager=machine_manager, backend=backend)
    run_manager = RemoteRunManager(
        session_manager=session_manager,
        file_manager=RemoteFileManager(
            machine_manager=machine_manager,
            session_manager=session_manager,
            backend=backend,
        ),
    )

    run = run_manager.once(machine_id="lab-gpu-01", command="exit-seven")

    assert run["status"] == "failed"
    assert run["command_result"]["exit_code"] == 7
    assert run["command_result"]["stderr"] == "failed\n"
    assert run["destroy_session_result"]["status"] == "destroyed"
    assert load_session_state(run["session_id"])["status"] == "destroyed"


def test_remote_runner_cli_machine_json_redacts_password(remote_state_dir, monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "remote-runner",
            "machine",
            "add",
            "--machine-id",
            "ops-01",
            "--host",
            "example.internal",
            "--user",
            "deploy",
            "--auth-type",
            "password",
            "--password",
            "secret-password",
            "--default-cwd",
            "/srv/app",
            "--json",
        ],
    )
    remote_cli_main()
    added = json.loads(capsys.readouterr().out)
    assert added["password"] == "***REDACTED***"

    monkeypatch.setattr(sys, "argv", ["remote-runner", "machine", "list", "--json"])
    remote_cli_main()
    listed = json.loads(capsys.readouterr().out)
    assert listed["summary"] == {"machine_count": 1}
    assert listed["machines"][0]["password"] == "***REDACTED***"
    assert "secret-password" not in json.dumps(listed)


def test_remote_runner_cli_machine_add_prompts_missing_password_fields(
    remote_state_dir,
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        sys,
        "argv",
        ["remote-runner", "machine", "add", "--json"],
    )
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            "\n".join(
                [
                    "ops-01",
                    "example.internal",
                    "2201",
                    "deploy",
                    "password",
                    "wsl",
                    "",
                    "/srv/app",
                ]
            )
            + "\n",
        ),
    )
    monkeypatch.setattr(
        "remote_runner.cli.getpass.getpass",
        lambda prompt, stream=None: "secret-password",
    )

    remote_cli_main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    state = load_machines_state()

    assert payload["machine_id"] == "ops-01"
    assert payload["port"] == 2201
    assert payload["password"] == "***REDACTED***"
    assert payload["startup_commands"] == ["wsl"]
    assert "Machine ID" not in captured.out
    assert "secret-password" not in captured.out
    assert "Machine ID" in captured.err
    assert state["machines"]["ops-01"]["password"] == "secret-password"
    assert state["machines"]["ops-01"]["startup_commands"] == ["wsl"]
    assert oct(os.stat(get_machines_file()).st_mode & 0o777) == "0o600"


def test_machine_add_duplicate_without_replace_preserves_existing(remote_state_dir, tmp_path):
    machine_manager = RemoteMachineManager()
    _add_key_machine(machine_manager, tmp_path)

    with pytest.raises(ValueError, match="already exists"):
        machine_manager.add(
            machine_id="lab-gpu-01",
            host="192.0.2.10",
            port=22,
            user="other",
            auth_type="key",
            key_path=str(_write_key(tmp_path)),
            default_cwd="/tmp",
        )

    assert machine_manager.show("lab-gpu-01")["host"] == "127.0.0.1"


def test_remote_runner_cli_interactive_replace_rejects_wrong_confirmation(
    remote_state_dir,
    monkeypatch,
    capsys,
):
    RemoteMachineManager().add(
        machine_id="ops-01",
        host="old.example.internal",
        port=22,
        user="deploy",
        auth_type="password",
        password="old-password",
        default_cwd="/srv/old",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["remote-runner", "machine", "add", "--replace", "--json"],
    )
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            "\n".join(
                [
                    "ops-01",
                    "new.example.internal",
                    "2202",
                    "deploy",
                    "password",
                    "",
                    "/srv/new",
                    "wrong-id",
                ]
            )
            + "\n",
        ),
    )
    monkeypatch.setattr(
        "remote_runner.cli.getpass.getpass",
        lambda prompt, stream=None: "new-password",
    )

    with pytest.raises(SystemExit) as exc:
        remote_cli_main()

    captured = capsys.readouterr()
    assert exc.value.code == 1
    assert "already exists and will be replaced" in captured.err
    assert json.loads(captured.out)["error"].find("requires exact confirmation") >= 0
    record = load_machines_state()["machines"]["ops-01"]
    assert record["host"] == "old.example.internal"
    assert record["password"] == "old-password"


def test_remote_runner_cli_interactive_replace_updates_machine_with_exact_confirmation(
    remote_state_dir,
    monkeypatch,
    capsys,
):
    created = RemoteMachineManager().add(
        machine_id="ops-01",
        host="old.example.internal",
        port=22,
        user="deploy",
        auth_type="password",
        password="old-password",
        default_cwd="/srv/old",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["remote-runner", "machine", "add", "--replace", "--json"],
    )
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            "\n".join(
                [
                    "ops-01",
                    "new.example.internal",
                    "2202",
                    "deploy",
                    "password",
                    "",
                    "/srv/new",
                    "ops-01",
                ]
            )
            + "\n",
        ),
    )
    monkeypatch.setattr(
        "remote_runner.cli.getpass.getpass",
        lambda prompt, stream=None: "new-password",
    )

    remote_cli_main()
    payload = json.loads(capsys.readouterr().out)
    record = load_machines_state()["machines"]["ops-01"]

    assert payload["host"] == "new.example.internal"
    assert payload["password"] == "***REDACTED***"
    assert record["host"] == "new.example.internal"
    assert record["port"] == 2202
    assert record["password"] == "new-password"
    assert record["created_at"] == created["created_at"]
    assert "updated_at" in record


def test_remote_runner_cli_noninteractive_replace_requires_confirmation(
    remote_state_dir,
    monkeypatch,
    capsys,
):
    RemoteMachineManager().add(
        machine_id="ops-01",
        host="old.example.internal",
        port=22,
        user="deploy",
        auth_type="password",
        password="old-password",
        default_cwd="/srv/old",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "remote-runner",
            "machine",
            "add",
            "--machine-id",
            "ops-01",
            "--host",
            "new.example.internal",
            "--user",
            "deploy",
            "--auth-type",
            "password",
            "--password",
            "new-password",
            "--default-cwd",
            "/srv/new",
            "--replace",
            "--json",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        remote_cli_main()

    assert exc.value.code == 1
    assert json.loads(capsys.readouterr().out)["error"].find("requires exact confirmation") >= 0
    assert load_machines_state()["machines"]["ops-01"]["host"] == "old.example.internal"


def test_remote_runner_cli_noninteractive_replace_with_confirmation(
    remote_state_dir,
    monkeypatch,
    capsys,
):
    created = RemoteMachineManager().add(
        machine_id="ops-01",
        host="old.example.internal",
        port=22,
        user="deploy",
        auth_type="password",
        password="old-password",
        default_cwd="/srv/old",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "remote-runner",
            "machine",
            "add",
            "--machine-id",
            "ops-01",
            "--host",
            "new.example.internal",
            "--user",
            "deploy",
            "--auth-type",
            "password",
            "--password",
            "new-password",
            "--default-cwd",
            "/srv/new",
            "--replace",
            "--confirm-replace",
            "ops-01",
            "--json",
        ],
    )

    remote_cli_main()
    payload = json.loads(capsys.readouterr().out)
    record = load_machines_state()["machines"]["ops-01"]

    assert payload["host"] == "new.example.internal"
    assert payload["password"] == "***REDACTED***"
    assert record["created_at"] == created["created_at"]
    assert "updated_at" in record


def test_remote_runner_cli_interactive_key_auth_validates_key_path(
    remote_state_dir,
    tmp_path,
    monkeypatch,
    capsys,
):
    key_path = _write_key(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["remote-runner", "machine", "add", "--json"],
    )
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            "\n".join(
                [
                    "lab-gpu-01",
                    "127.0.0.1",
                    "2222",
                    "ely",
                    "key",
                    str(key_path),
                    "",
                    "/home/ely/project",
                ]
            )
            + "\n",
        ),
    )

    remote_cli_main()
    payload = json.loads(capsys.readouterr().out)

    assert payload["machine_id"] == "lab-gpu-01"
    assert payload["auth_type"] == "key"
    assert payload["key_path"] == str(key_path)


def test_remote_runner_cli_configure_startup_preserves_credentials(
    remote_state_dir,
    monkeypatch,
    capsys,
):
    created = RemoteMachineManager().add(
        machine_id="windows-01",
        host="windows.example.internal",
        port=22,
        user="ely",
        auth_type="password",
        password="secret-password",
        default_cwd="C:/Users/example",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "remote-runner",
            "machine",
            "configure-startup",
            "windows-01",
            "--startup-command",
            "wsl",
            "--default-cwd",
            "/mnt/c/Users/example/Desktop/SSHRunner",
            "--json",
        ],
    )

    remote_cli_main()
    payload = json.loads(capsys.readouterr().out)
    record = load_machines_state()["machines"]["windows-01"]

    assert payload["startup_commands"] == ["wsl"]
    assert payload["default_cwd"] == "/mnt/c/Users/example/Desktop/SSHRunner"
    assert payload["password"] == "***REDACTED***"
    assert record["password"] == "secret-password"
    assert record["created_at"] == created["created_at"]
    assert "updated_at" in record


def test_machine_configure_path_map_preserves_credentials_and_maps_paths(remote_state_dir):
    manager = RemoteMachineManager()
    created = manager.add(
        machine_id="windows-01",
        host="windows.example.internal",
        port=22,
        user="ely",
        auth_type="password",
        password="secret-password",
        default_cwd="/mnt/c/Users/example/Desktop/SSHRunner",
        startup_commands=["wsl"],
    )

    updated = manager.configure_path_map(
        machine_id="windows-01",
        command_prefix="/mnt/c/Users/example/Desktop/SSHRunner",
        file_prefix="C:/Users/example/Desktop/SSHRunner",
    )
    record = load_machines_state()["machines"]["windows-01"]
    machine = manager.get("windows-01")

    assert updated["path_mappings"] == [
        {
            "command_prefix": "/mnt/c/Users/example/Desktop/SSHRunner",
            "file_prefix": "C:/Users/example/Desktop/SSHRunner",
        }
    ]
    assert updated["password"] == "***REDACTED***"
    assert record["password"] == "secret-password"
    assert record["created_at"] == created["created_at"]
    assert "updated_at" in record
    assert (
        machine.map_file_path("/mnt/c/Users/example/Desktop/SSHRunner/probe.txt")
        == "C:/Users/example/Desktop/SSHRunner/probe.txt"
    )
    assert (
        machine.map_file_path("/mnt/c/Users/example/Desktop/SSHRunner")
        == "C:/Users/example/Desktop/SSHRunner"
    )
    assert machine.map_file_path("/home/ely/project") == "/home/ely/project"


def test_remote_runner_cli_configure_path_map_outputs_json(
    remote_state_dir,
    monkeypatch,
    capsys,
):
    RemoteMachineManager().add(
        machine_id="windows-01",
        host="windows.example.internal",
        port=22,
        user="ely",
        auth_type="password",
        password="secret-password",
        default_cwd="/mnt/c/Users/example/Desktop/SSHRunner",
        startup_commands=["wsl"],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "remote-runner",
            "machine",
            "configure-path-map",
            "windows-01",
            "--command-prefix",
            "/mnt/c/Users/example/Desktop/SSHRunner",
            "--file-prefix",
            "C:/Users/example/Desktop/SSHRunner",
            "--json",
        ],
    )

    remote_cli_main()
    payload = json.loads(capsys.readouterr().out)

    assert payload["path_mappings"] == [
        {
            "command_prefix": "/mnt/c/Users/example/Desktop/SSHRunner",
            "file_prefix": "C:/Users/example/Desktop/SSHRunner",
        }
    ]
    assert payload["password"] == "***REDACTED***"


class FakeInteractiveChannel:
    def __init__(self):
        self.sent = []
        self.output = b""
        self.begin_marker = ""

    def send(self, text):
        line = text.rstrip("\r\n")
        self.sent.append(line)
        if "printf" in text and "__REMOTE_RUNNER_BEGIN_" in text:
            self.begin_marker = text.split("\\n")[1]
        if "printf" in text and "__REMOTE_RUNNER_EXIT_" in text:
            marker = text.split("\\n")[1].split(":%s")[0]
            command = self.sent[-2]
            self.output += (
                "Microsoft Windows [Version 10.0.26200.8246]\r\n"
                "(c) Microsoft Corporation. All rights reserved.\r\n"
                "user@WINDOWS-HOST C:\\Users\\example>wsl\r\n"
                "wsl: detected localhost proxy configuration\r\n"
                "(base) root@WindowsHost:/mnt/c/Users/example# "
                "export PS1='' 2>/dev/null || true\r\n"
                "(base) root@WindowsHost:/mnt/c/Users/example# "
                "stty -echo 2>/dev/null || true\r\n"
                "(base) root@WindowsHost:/mnt/c/Users/example# "
                "cd /mnt/c/Users/example/Desktop/SSHRunner\r\n"
                "(base) root@WindowsHost:/mnt/c/Users/example/Desktop/SSHRunner# "
                f"printf '\\n{self.begin_marker}\\n'\r\n"
                f"{self.begin_marker}\r\n"
                "(base) root@WindowsHost:/mnt/c/Users/example/Desktop/SSHRunner# "
                f"{command}\r\n"
                "/mnt/c/Users/example/Desktop/SSHRunner\r\n"
                "remote-runner-ok\r\n"
                "(base) root@WindowsHost:/mnt/c/Users/example/Desktop/SSHRunner# "
                f"printf '\\n{marker}:%s\\n' $?\r\n"
                f"{marker}:0\r\n"
            ).encode("utf-8")

    def recv_ready(self):
        return bool(self.output)

    def recv(self, size):
        chunk = self.output[:size]
        self.output = self.output[size:]
        return chunk

    def exit_status_ready(self):
        return False


class FakeInteractiveClient:
    def __init__(self):
        self.channel = FakeInteractiveChannel()
        self.closed = False

    def invoke_shell(self, width=80, height=24):
        return self.channel

    def close(self):
        self.closed = True


def test_backend_startup_commands_use_interactive_shell(remote_state_dir, tmp_path):
    key_path = _write_key(tmp_path)
    machine = RemoteMachineManager().add(
        machine_id="windows-01",
        host="windows.example.internal",
        port=22,
        user="ely",
        auth_type="key",
        key_path=str(key_path),
        default_cwd="/mnt/c/Users/example/Desktop/SSHRunner",
        startup_commands=["wsl"],
    )
    remote_machine = RemoteMachineManager()
    # Store the machine in state-backed manager so from_dict coverage remains consistent.
    assert machine["startup_commands"] == ["wsl"]
    client = FakeInteractiveClient()
    backend = ParamikoRemoteBackend()
    backend._connect = lambda *args, **kwargs: client  # type: ignore[method-assign]

    result = backend.run(
        remote_machine.get("windows-01"),
        "/mnt/c/Users/example/Desktop/SSHRunner",
        "pwd && printf remote-runner-ok",
    )

    assert result.exit_code == 0
    assert result.stdout == "/mnt/c/Users/example/Desktop/SSHRunner\nremote-runner-ok\n"
    assert "__REMOTE_RUNNER_EXIT_" not in result.stdout
    assert "Microsoft Windows" not in result.stdout
    assert "wsl:" not in result.stdout
    assert "cd /mnt/c/Users/example/Desktop/SSHRunner" not in result.stdout
    assert "pwd && printf remote-runner-ok" not in result.stdout
    assert client.channel.sent[0] == "wsl"
    assert client.channel.sent[1] == "export PS1='' 2>/dev/null || true"
    assert client.channel.sent[2] == "stty -echo 2>/dev/null || true"
    assert client.channel.sent[3] == "cd /mnt/c/Users/example/Desktop/SSHRunner"
    assert client.channel.sent[5] == "pwd && printf remote-runner-ok"
    assert client.closed is True


class FakeSFTPAttr:
    def __init__(self, filename, mode, size=0, mtime=1778198400):
        self.filename = filename
        self.st_mode = mode
        self.st_size = size
        self.st_mtime = mtime


class FakeSFTPClient:
    def __init__(self):
        self.put_calls = []
        self.get_calls = []
        self.listdir_calls = []
        self.stat_calls = []
        self.closed = False

    def stat(self, path):
        self.stat_calls.append(path)
        if path.endswith(".txt"):
            return FakeSFTPAttr(Path(path).name, stat.S_IFREG | 0o644, size=11)
        return FakeSFTPAttr(Path(path).name, stat.S_IFDIR | 0o755)

    def put(self, local_path, remote_path):
        self.put_calls.append((local_path, remote_path))

    def get(self, remote_path, local_path):
        self.get_calls.append((remote_path, local_path))
        Path(local_path).write_text("hello world")

    def listdir_attr(self, remote_path):
        self.listdir_calls.append(remote_path)
        return [FakeSFTPAttr("result.txt", stat.S_IFREG | 0o644, size=11)]

    def close(self):
        self.closed = True


class FakeSFTPOnlyClient:
    def __init__(self, sftp):
        self.sftp = sftp
        self.closed = False

    def open_sftp(self):
        return self.sftp

    def close(self):
        self.closed = True


def test_backend_applies_path_mapping_for_sftp_operations(remote_state_dir, tmp_path):
    key_path = _write_key(tmp_path)
    manager = RemoteMachineManager()
    manager.add(
        machine_id="windows-01",
        host="windows.example.internal",
        port=22,
        user="ely",
        auth_type="key",
        key_path=str(key_path),
        default_cwd="/mnt/c/Users/example/Desktop/SSHRunner",
        startup_commands=["wsl"],
    )
    manager.configure_path_map(
        "windows-01",
        "/mnt/c/Users/example/Desktop/SSHRunner",
        "C:/Users/example/Desktop/SSHRunner",
    )
    local_file = tmp_path / "probe.txt"
    local_file.write_text("hello world")
    download_file = tmp_path / "download.txt"
    sftp = FakeSFTPClient()
    client = FakeSFTPOnlyClient(sftp)
    backend = ParamikoRemoteBackend()
    backend._connect = lambda *args, **kwargs: client  # type: ignore[method-assign]
    machine = manager.get("windows-01")

    put = backend.put(
        machine,
        str(local_file),
        "/mnt/c/Users/example/Desktop/SSHRunner/probe.txt",
    )
    listing = backend.list(machine, "/mnt/c/Users/example/Desktop/SSHRunner")
    got = backend.get(
        machine,
        "/mnt/c/Users/example/Desktop/SSHRunner/probe.txt",
        str(download_file),
    )

    assert put["size_bytes"] == len("hello world")
    assert got["size_bytes"] == len("hello world")
    assert sftp.put_calls[-1][1] == "C:/Users/example/Desktop/SSHRunner/probe.txt"
    assert sftp.listdir_calls[-1] == "C:/Users/example/Desktop/SSHRunner"
    assert sftp.get_calls[-1][0] == "C:/Users/example/Desktop/SSHRunner/probe.txt"
    assert listing["entries"][0]["path"] == "/mnt/c/Users/example/Desktop/SSHRunner/result.txt"
    assert client.closed is True
