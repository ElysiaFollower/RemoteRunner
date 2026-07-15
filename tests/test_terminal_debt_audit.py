import base64
import io
import threading
from types import SimpleNamespace

import pytest

from remote_runner.remote_backend import ParamikoRemoteBackend, RemoteCommandResult
from remote_runner.remote_machine import RemoteMachine, RemoteMachineManager
from remote_runner.remote_run import RemoteRunManager
from remote_runner.remote_session import RemoteSessionManager
from remote_runner.remote_state import load_session_state


class _BatchSeparationBackend:
    def __init__(self):
        self.run_calls = []
        self.background_calls = []
        self.pane_inputs = []

    def create_terminal(
        self,
        machine,
        cwd,
        terminal_id,
        terminal_name=None,
        transcript_file_local=None,
        **kwargs,
    ):
        return {
            "backend": "tmux",
            "remote_terminal_name": f"rr_{terminal_id}",
            "transcript_mode": "append-only",
            "remote_transcript_file": f"/tmp/{terminal_id}.log",
        }

    def terminal_exists(self, machine, terminal_record):
        return True

    def capture_terminal(self, machine, terminal_record):
        return {"status": "active", "transcript": ""}

    def destroy_terminal(self, machine, terminal_record):
        return {"destroy_result": "destroyed"}

    def send_terminal_input(self, machine, terminal_record, input_text, enter=True):
        self.pane_inputs.append(input_text)
        return {"input_sent": True}

    def start_session_command(self, *args, **kwargs):
        raise AssertionError("structured command reached the live terminal protocol")

    def run(self, machine, cwd, command, timeout=300):
        self.run_calls.append((machine.machine_id, cwd, command, timeout))
        return RemoteCommandResult(
            stdout="batch-output\n",
            stderr="",
            exit_code=0,
            started_at="2026-07-15T00:00:00Z",
            ended_at="2026-07-15T00:00:01Z",
            duration_ms=1000,
        )

    def start_background(self, machine, cwd, command, command_id, timeout=15):
        self.background_calls.append((machine.machine_id, cwd, command, command_id, timeout))
        state_dir = f"{cwd}/.remote-runner/commands/{command_id}"
        return {
            "remote_state_dir": state_dir,
            "remote_stdout_file": f"{state_dir}/stdout.log",
            "remote_stderr_file": f"{state_dir}/stderr.log",
            "remote_status_file": f"{state_dir}/status",
            "remote_pid_file": f"{state_dir}/pid",
            "remote_exit_code_file": f"{state_dir}/exit_code",
            "remote_ended_at_file": f"{state_dir}/ended_at",
            "remote_pid": "123",
        }


def _add_ssh_tmux_machine(manager, tmp_path):
    key = tmp_path / "id_test"
    key.write_text("test-only", encoding="utf-8")
    manager.add(
        machine_id="batch-linux",
        host="127.0.0.1",
        user="test",
        auth_type="key",
        key_path=str(key),
        default_cwd="/tmp/work",
        backend="ssh-tmux",
    )


def test_ssh_tmux_exec_uses_batch_transport_without_pane_input(tmp_path, monkeypatch):
    monkeypatch.setenv("REMOTE_RUNNER_STATE_DIR", str(tmp_path / "state"))
    machines = RemoteMachineManager()
    _add_ssh_tmux_machine(machines, tmp_path)
    backend = _BatchSeparationBackend()
    manager = RemoteSessionManager(machine_manager=machines, backend=backend)
    session_id = manager.create("batch-linux")["session_id"]

    result = manager.exec(session_id, "printf batch", timeout=17)

    assert result["stdout"] == "batch-output\n"
    assert result["command_backend"] == "direct_ssh"
    assert backend.run_calls == [("batch-linux", "/tmp/work", "printf batch", 17)]
    assert backend.pane_inputs == []


def test_ssh_tmux_background_uses_batch_transport_without_pane_input(tmp_path, monkeypatch):
    monkeypatch.setenv("REMOTE_RUNNER_STATE_DIR", str(tmp_path / "state"))
    machines = RemoteMachineManager()
    _add_ssh_tmux_machine(machines, tmp_path)
    backend = _BatchSeparationBackend()
    manager = RemoteSessionManager(machine_manager=machines, backend=backend)
    session_id = manager.create("batch-linux")["session_id"]

    result = manager.exec(session_id, "sleep 30", mode="background")

    assert result["status"] == "running"
    assert result["command_backend"] == "direct_ssh_background"
    assert len(backend.background_calls) == 1
    assert backend.pane_inputs == []


def test_run_once_uses_batch_transport_without_session_exec(tmp_path, monkeypatch):
    monkeypatch.setenv("REMOTE_RUNNER_STATE_DIR", str(tmp_path / "state"))
    machines = RemoteMachineManager()
    _add_ssh_tmux_machine(machines, tmp_path)
    backend = _BatchSeparationBackend()
    sessions = RemoteSessionManager(machine_manager=machines, backend=backend)
    monkeypatch.setattr(
        sessions,
        "exec",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("run once delegated to session exec")
        ),
    )
    manager = RemoteRunManager(session_manager=sessions)

    result = manager.once("batch-linux", "printf batch", timeout=23)

    assert result["status"] == "succeeded"
    assert result["command_result"]["stdout"] == "batch-output\n"
    assert result["command_result"]["command_backend"] == "direct_ssh"
    assert backend.run_calls == [("batch-linux", "/tmp/work", "printf batch", 23)]
    assert backend.pane_inputs == []


def test_openssh_file_get_rejects_without_terminal_protocol(tmp_path, monkeypatch):
    backend = ParamikoRemoteBackend()
    machine = RemoteMachine(
        machine_id="interactive",
        host="",
        port=22,
        user="",
        auth_type="manual",
        default_cwd="~",
        startup_commands=[],
        path_mappings=[],
        platform="linux",
        backend="openssh-pty",
        shell="bash",
        ssh_alias="interactive",
    )
    pane_writes = []
    monkeypatch.setattr(
        backend,
        "_send_local_tmux_input",
        lambda *args, **kwargs: pane_writes.append((args, kwargs)),
    )

    with pytest.raises(RuntimeError, match="independent file transport"):
        backend.get(
            machine,
            "/remote/file",
            str(tmp_path / "file"),
        )

    assert pane_writes == []


class _StatusChannel:
    def recv_exit_status(self):
        return 0


class _StatusStream(io.BytesIO):
    def __init__(self):
        super().__init__(b"")
        self.channel = _StatusChannel()


class _CountingRemoteFile(io.BytesIO):
    def __init__(self, data, tracker):
        super().__init__(data)
        self.tracker = tracker

    def read(self, size=-1):
        data = super().read(size)
        self.tracker["bytes_read"] += len(data)
        return data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _CountingSFTP:
    def __init__(self, storage, tracker):
        self.storage = storage
        self.tracker = tracker

    def stat(self, path):
        return SimpleNamespace(st_size=len(self.storage[path]))

    def open(self, path, mode):
        return _CountingRemoteFile(self.storage[path], self.tracker)

    def close(self):
        pass


class _CaptureClient:
    def __init__(self, sftp):
        self.sftp = sftp

    def exec_command(self, command):
        return None, _StatusStream(), _StatusStream()

    def open_sftp(self):
        return self.sftp

    def close(self):
        pass


def test_remote_transcript_reads_only_delta_and_preserves_split_utf8(monkeypatch):
    path = "/remote/terminal.log"
    prefix = b"old-history\n" * 1000
    snowman = "雪".encode("utf-8")
    storage = {path: prefix + snowman[:2]}
    tracker = {"bytes_read": 0}
    sftp = _CountingSFTP(storage, tracker)
    backend = ParamikoRemoteBackend()
    monkeypatch.setattr(backend, "_connect", lambda machine: _CaptureClient(sftp))
    machine = RemoteMachine(
        machine_id="remote",
        host="example.invalid",
        port=22,
        user="test",
        auth_type="password",
        password="test-only",
        default_cwd="/tmp",
        startup_commands=[],
        path_mappings=[],
        backend="ssh-tmux",
        shell="bash",
    )
    record = {
        "remote_terminal_name": "rr_test",
        "transcript_mode": "append-only",
        "remote_transcript_file": path,
        "remote_transcript_cursor_bytes": 0,
    }

    first = backend.capture_terminal(machine, record)
    assert first["transcript_delta"] == prefix.decode("utf-8")
    assert tracker["bytes_read"] == len(prefix) + 2
    record.update(first)

    storage[path] += snowman[2:] + b"\ntail\n"
    tracker["bytes_read"] = 0
    second = backend.capture_terminal(machine, record)
    assert second["transcript_delta"] == "雪\ntail\n"
    assert tracker["bytes_read"] == 7
    record.update(second)

    tracker["bytes_read"] = 0
    empty = backend.capture_terminal(machine, record)
    assert empty["transcript_delta"] == ""
    assert tracker["bytes_read"] == 0
    assert base64.b64decode(empty["remote_transcript_utf8_tail_b64"]) == b""


class _ManagerDeltaBackend(_BatchSeparationBackend):
    def __init__(self):
        super().__init__()
        self.captures = iter(
            [
                {
                    "status": "active",
                    "transcript_delta": "first\n",
                    "remote_transcript_cursor_bytes": 6,
                    "remote_transcript_utf8_tail_b64": "",
                },
                {
                    "status": "active",
                    "transcript_delta": "second\n",
                    "remote_transcript_cursor_bytes": 13,
                    "remote_transcript_utf8_tail_b64": "",
                },
            ]
        )

    def capture_terminal(self, machine, terminal_record):
        return next(self.captures)


def test_session_manager_appends_remote_delta_and_persists_both_cursors(tmp_path, monkeypatch):
    monkeypatch.setenv("REMOTE_RUNNER_STATE_DIR", str(tmp_path / "state"))
    machines = RemoteMachineManager()
    _add_ssh_tmux_machine(machines, tmp_path)
    backend = _ManagerDeltaBackend()
    manager = RemoteSessionManager(machine_manager=machines, backend=backend)
    created = manager.create("batch-linux")

    first = manager.read(created["session_id"])
    second = manager.read(created["session_id"], since=first["cursor"])
    public = manager.show(created["session_id"])
    state = load_session_state(created["session_id"])

    assert first["transcript"] == "first\n"
    assert second["transcript"] == "second\n"
    assert second["cursor"] == 13
    assert public["transcript_cursor"] == 13
    assert state["remote_transcript_cursor_bytes"] == 13
    with open(state["transcript_file_local"], encoding="utf-8") as transcript:
        assert transcript.read() == "first\nsecond\n"


class _ConcurrentDeltaBackend(_BatchSeparationBackend):
    def __init__(self):
        super().__init__()
        self.barrier = threading.Barrier(2)

    def capture_terminal(self, machine, terminal_record):
        self.barrier.wait(timeout=2)
        return {
            "status": "active",
            "transcript_delta": "once\n",
            "remote_transcript_cursor_bytes": 5,
            "remote_transcript_utf8_tail_b64": "",
        }


def test_concurrent_remote_reads_do_not_append_the_same_delta_twice(tmp_path, monkeypatch):
    monkeypatch.setenv("REMOTE_RUNNER_STATE_DIR", str(tmp_path / "state"))
    machines = RemoteMachineManager()
    _add_ssh_tmux_machine(machines, tmp_path)
    backend = _ConcurrentDeltaBackend()
    manager = RemoteSessionManager(machine_manager=machines, backend=backend)
    created = manager.create("batch-linux")
    errors = []

    def read():
        try:
            manager.read(created["session_id"])
        except BaseException as exc:
            errors.append(exc)

    readers = [threading.Thread(target=read) for _ in range(2)]
    for reader in readers:
        reader.start()
    for reader in readers:
        reader.join(timeout=3)

    assert errors == []
    assert all(not reader.is_alive() for reader in readers)
    state = load_session_state(created["session_id"])
    with open(state["transcript_file_local"], encoding="utf-8") as transcript:
        assert transcript.read() == "once\n"
    assert state["remote_transcript_cursor_bytes"] == 5


def test_windows_wait_polls_until_result_is_terminal(monkeypatch):
    backend = ParamikoRemoteBackend()
    machine = RemoteMachine(
        machine_id="windows",
        host="127.0.0.1",
        port=22,
        user="test",
        auth_type="password",
        password="test-only",
        default_cwd="C:/work",
        startup_commands=[],
        path_mappings=[],
        platform="windows",
        backend="windows-agent",
        shell="pwsh",
    )
    results = iter(
        [
            {"status": "running"},
            {"status": "exited", "exit_code": 0, "stdout": "done\n", "stderr": ""},
        ]
    )
    calls = []

    def inspect(**kwargs):
        calls.append(kwargs["command_record"])
        return next(results)

    monkeypatch.setattr(backend, "inspect_session_command", inspect)
    monkeypatch.setattr("remote_runner.remote_backend.time.sleep", lambda _: None)

    result = backend.wait_session_command(machine, {"command_id": "cmd_test"}, timeout=1)

    assert result["status"] == "exited"
    assert result["stdout"] == "done\n"
    assert len(calls) == 2


def test_windows_interrupt_is_explicitly_unsupported():
    backend = ParamikoRemoteBackend()
    machine = RemoteMachine(
        machine_id="windows",
        host="127.0.0.1",
        port=22,
        user="test",
        auth_type="password",
        password="test-only",
        default_cwd="C:/work",
        startup_commands=[],
        path_mappings=[],
        platform="windows",
        backend="windows-agent",
        shell="pwsh",
    )

    with pytest.raises(RuntimeError, match="not yet supported for windows-agent"):
        backend.interrupt_terminal(machine, {"session_id": "sess_test"})


def test_windows_destroy_returns_structured_result(monkeypatch):
    backend = ParamikoRemoteBackend()
    machine = RemoteMachine(
        machine_id="windows",
        host="127.0.0.1",
        port=22,
        user="test",
        auth_type="password",
        password="test-only",
        default_cwd="C:/work",
        startup_commands=[],
        path_mappings=[],
        platform="windows",
        backend="windows-agent",
        shell="pwsh",
    )
    sftp = SimpleNamespace(close=lambda: None)
    client = SimpleNamespace(open_sftp=lambda: sftp, close=lambda: None)
    monkeypatch.setattr(backend, "_connect", lambda machine: client)
    monkeypatch.setattr(backend, "_write_remote_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(backend, "_wait_for_remote_json", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        backend,
        "_read_remote_json",
        lambda *args, **kwargs: {"status": "stopped"},
    )
    monkeypatch.setattr(backend, "_run_windows_powershell", lambda *args, **kwargs: ("", "", 0))
    monkeypatch.setattr(backend, "_windows_delete_task_script", lambda task_name: "cleanup")

    result = backend._destroy_windows_agent_terminal(
        machine,
        {
            "windows_agent_dir": "C:/work/.remote-runner/windows-agent/sess_test",
            "remote_terminal_name": "RemoteRunner_sess_test",
        },
    )

    assert result == {"destroy_result": "destroyed"}
