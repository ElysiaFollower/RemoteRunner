import io
import os
import re
import shutil
import time
from pathlib import Path

import pytest

from remote_runner.remote_backend import ParamikoRemoteBackend
from remote_runner.cli import build_parser
from remote_runner.remote_machine import RemoteMachine, RemoteMachineManager
from remote_runner.remote_session import RemoteSessionManager
from remote_runner.remote_state import load_session_state, remote_state_lock, save_session_state

ANSI_CSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _ends_with_visible_prompt(transcript: str, prompt: str) -> bool:
    return ANSI_CSI.sub("", transcript).endswith(prompt)


def _wait_for_transcript(
    manager: RemoteSessionManager,
    session_id: str,
    expected: str,
    *,
    since: int = 0,
    timeout: float = 5.0,
):
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        latest = manager.read(session_id, since=since)
        if expected in latest["transcript"]:
            return latest
        time.sleep(0.05)
    pytest.fail(f"timed out waiting for {expected!r}; last read: {latest!r}")


@pytest.fixture(params=["bash", "zsh"])
def local_terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request):
    shell = shutil.which(request.param)
    if shell is None:
        pytest.skip(f"{request.param} is not installed")
    if shutil.which("tmux") is None:
        pytest.skip("tmux is not installed")

    state_dir = tmp_path / "state"
    monkeypatch.setenv("REMOTE_RUNNER_STATE_DIR", str(state_dir))

    ssh_shim = tmp_path / f"local-ssh-{request.param}"
    shell_args = "--noprofile --norc" if request.param == "bash" else "-f"
    ssh_shim.write_text(f"#!/bin/sh\nexec {shell} {shell_args}\n", encoding="utf-8")
    ssh_shim.chmod(0o700)

    machines = RemoteMachineManager()
    machines.add(
        machine_id=f"local-{request.param}",
        auth_type="manual",
        backend="openssh-pty",
        ssh_alias="ignored-by-local-test-shim",
        platform="linux",
        shell=request.param,
        default_cwd="~",
    )
    backend = ParamikoRemoteBackend()
    backend._ssh_binary = lambda: str(ssh_shim)  # type: ignore[method-assign]
    manager = RemoteSessionManager(machine_manager=machines, backend=backend)
    created = manager.create(f"local-{request.param}")
    try:
        yield manager, created
    finally:
        try:
            manager.destroy(created["session_id"])
        except Exception:
            tmux_name = created.get("remote_backend_name")
            if tmux_name:
                os.system(f"tmux kill-session -t {tmux_name!s} >/dev/null 2>&1")


def test_literal_input_is_visible_and_shell_state_persists(local_terminal, tmp_path: Path):
    manager, created = local_terminal
    session_id = created["session_id"]

    command = "printf 'RR_VISIBLE_%s\\n' TOKEN"
    sent = manager.send(session_id, command)
    first = _wait_for_transcript(manager, session_id, "RR_VISIBLE_TOKEN")

    assert sent["input"] == command
    assert command in first["transcript"]
    assert first["transcript"].count("RR_VISIBLE_TOKEN") == 1
    assert created["transcript_mode"] == "append-only"

    empty = manager.read(session_id, since=first["cursor"])
    assert empty["transcript"] == ""

    workdir = tmp_path / "persistent-cwd"
    workdir.mkdir()
    manager.send(session_id, f"cd {workdir}")
    manager.send(session_id, "export RR_PERSISTED=terminal-state")
    state_command = 'printf \'RR_STATE=%s|%s\\n\' "$PWD" "$RR_PERSISTED"'
    manager.send(session_id, state_command)
    persisted = _wait_for_transcript(
        manager,
        session_id,
        f"RR_STATE={workdir}|terminal-state",
        since=first["cursor"],
    )

    assert state_command in persisted["transcript"]


def test_interrupt_recovers_the_same_terminal(local_terminal):
    manager, created = local_terminal
    session_id = created["session_id"]

    manager.send(session_id, "printf 'RR_%s\\n' SLEEPING; sleep 30")
    sleeping = _wait_for_transcript(manager, session_id, "RR_SLEEPING")
    interrupted = manager.interrupt(session_id)
    assert interrupted["interrupt_sent"] is True

    manager.send(session_id, "printf 'RR_AFTER_INTERRUPT\\n'")
    recovered = _wait_for_transcript(
        manager,
        session_id,
        "RR_AFTER_INTERRUPT",
        since=sleeping["cursor"],
    )
    assert "RR_AFTER_INTERRUPT" in recovered["transcript"]


def test_long_output_remains_append_only_across_repeated_reads(local_terminal):
    manager, created = local_terminal
    session_id = created["session_id"]
    command = "i=0; while [ $i -lt 400 ]; do " "printf 'RR_LONG_%04d\\n' \"$i\"; i=$((i+1)); done"

    manager.send(session_id, command)
    long_read = _wait_for_transcript(manager, session_id, "RR_LONG_0399")
    assert len(re.findall(r"RR_LONG_\d{4}", long_read["transcript"])) == 400
    assert manager.read(session_id, since=long_read["cursor"])["transcript"] == ""

    manager.send(session_id, "printf 'RR_TAIL_%s\\n' ok")
    tail = _wait_for_transcript(
        manager,
        session_id,
        "RR_TAIL_ok",
        since=long_read["cursor"],
    )
    assert "RR_LONG_0000" not in tail["transcript"]


def test_explicit_tail_contains_visible_terminal_input_and_output(local_terminal):
    manager, created = local_terminal
    session_id = created["session_id"]
    command = "printf 'RR_TAIL_VISIBLE_%s\\n' yes"

    manager.send(session_id, command)
    _wait_for_transcript(manager, session_id, "RR_TAIL_VISIBLE_yes")
    observed = manager.tail(session_id, tail_bytes=512)

    assert command in observed["transcript"]
    assert "RR_TAIL_VISIBLE_yes" in observed["transcript"]
    assert observed["next_cursor"] == observed["last_cursor"]


def test_raw_terminal_records_prompt_before_next_shell_command(local_terminal):
    manager, created = local_terminal
    session_id = created["session_id"]
    prompt = "RR_PROMPT_V3> "

    manager.send(session_id, f"PS1='{prompt}'")
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        observed = manager.tail(session_id, tail_bytes=1024)
        if _ends_with_visible_prompt(observed["transcript"], prompt):
            break
        time.sleep(0.05)
    else:
        pytest.fail(f"prompt did not become visible; last tail: {observed!r}")

    command = "printf 'RR_PROMPT_OUTPUT\\n'"
    sent = manager.send(session_id, command)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        observed = manager.tail(session_id, tail_bytes=1024)
        if (
            "RR_PROMPT_OUTPUT" in observed["transcript"]
            and _ends_with_visible_prompt(observed["transcript"], prompt)
            and observed["last_cursor"] > sent["start_cursor"]
        ):
            break
        time.sleep(0.05)
    else:
        pytest.fail(f"command output and returned prompt not visible; last tail: {observed!r}")

    assert command in observed["transcript"]


def test_repeated_failures_keep_input_visible_and_cursor_monotonic(local_terminal):
    manager, created = local_terminal
    session_id = created["session_id"]
    manager.send(session_id, "set +e")
    cursor = manager.read(session_id)["cursor"]

    for index in range(20):
        command = f"false; printf 'RR_STRESS_{index:02d}\\n'"
        manager.send(session_id, command)
        read = _wait_for_transcript(
            manager,
            session_id,
            f"RR_STRESS_{index:02d}",
            since=cursor,
        )
        assert command in read["transcript"]
        assert read["cursor"] > cursor
        assert "__REMOTE_RUNNER_CMD_" not in read["transcript"]
        assert 'eval "$__rr_command"' not in read["transcript"]
        cursor = read["cursor"]

    manager.send(session_id, "printf 'RR_STRESS_ALIVE\\n'")
    alive = _wait_for_transcript(manager, session_id, "RR_STRESS_ALIVE", since=cursor)
    assert "RR_STRESS_ALIVE" in alive["transcript"]


def test_openssh_pty_exec_is_rejected_without_writing_to_terminal(local_terminal):
    manager, created = local_terminal
    session_id = created["session_id"]
    before = manager.read(session_id)

    with pytest.raises(RuntimeError, match="session send"):
        manager.exec(session_id, "printf 'MUST_NOT_REACH_TERMINAL\\n'")

    time.sleep(0.1)
    after = manager.read(session_id, since=before["cursor"])
    assert "MUST_NOT_REACH_TERMINAL" not in after["transcript"]
    assert "__REMOTE_RUNNER_CMD_" not in after["transcript"]
    assert 'eval "$__rr_command"' not in after["transcript"]


def test_terminal_send_remains_available_during_independent_batch_work(local_terminal):
    manager, created = local_terminal
    session_id = created["session_id"]
    with remote_state_lock():
        session = load_session_state(session_id)
        session["busy"] = True
        save_session_state(session)

    manager.send(session_id, "printf 'SENT_DURING_BATCH\\n'")

    with remote_state_lock():
        session = load_session_state(session_id)
        session["busy"] = False
        save_session_state(session)
    transcript = _wait_for_transcript(manager, session_id, "SENT_DURING_BATCH")
    assert "SENT_DURING_BATCH" in transcript["transcript"]


def test_send_rejects_multiline_batch_input(local_terminal):
    manager, created = local_terminal
    session_id = created["session_id"]

    with pytest.raises(ValueError, match="one terminal line"):
        manager.send(session_id, "printf first\nprintf second")

    transcript = manager.read(session_id)["transcript"]
    assert "printf first" not in transcript


def test_cli_exposes_session_interrupt():
    args = build_parser().parse_args(["session", "interrupt", "--session", "demo-shell", "--json"])
    assert args.session == "demo-shell"
    assert args.func.__name__ == "cmd_session_interrupt"


class _FakeChannel:
    def __init__(self, exit_code: int = 0):
        self.exit_code = exit_code

    def recv_exit_status(self):
        return self.exit_code


class _FakeSSHStream(io.BytesIO):
    def __init__(self, content: bytes = b"", exit_code: int = 0):
        super().__init__(content)
        self.channel = _FakeChannel(exit_code)


class _FakeCreateClient:
    def __init__(self):
        self.commands = []
        self.closed = False

    def exec_command(self, command):
        self.commands.append(command)
        if len(self.commands) == 1:
            return None, _FakeSSHStream(b"/home/test"), _FakeSSHStream()
        return None, _FakeSSHStream(b"rr_sess_test\n"), _FakeSSHStream()

    def close(self):
        self.closed = True


def test_remote_tmux_create_configures_append_only_transcript(monkeypatch):
    backend = ParamikoRemoteBackend()
    client = _FakeCreateClient()
    monkeypatch.setattr(backend, "_connect", lambda machine: client)
    machine = RemoteMachine(
        machine_id="test-linux",
        host="example.invalid",
        port=22,
        user="test",
        auth_type="password",
        password="test-only",
        default_cwd="/tmp/work",
        startup_commands=[],
        path_mappings=[],
        platform="linux",
        backend="ssh-tmux",
        shell="bash",
    )

    created = backend.create_terminal(
        machine=machine,
        cwd="/tmp/work",
        terminal_id="sess_test",
        transcript_file_local="/tmp/not-used-by-remote",
    )

    assert created["transcript_mode"] == "append-only"
    assert created["remote_transcript_file"] == (
        "/home/test/.remote-runner/sessions/sess_test/terminal.log"
    )
    assert "tmux pipe-pane -O" in client.commands[1]
    assert "chmod 600" in client.commands[1]
    assert client.closed is True
