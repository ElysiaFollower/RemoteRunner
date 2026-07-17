import fcntl
import os
import pty
from pathlib import Path
import shlex
import struct
import subprocess
import termios
import time
from typing import Any, Dict


def test_recorder_starts_before_shell_and_preserves_raw_bytes(
    rr_env: Dict[str, Any], wait_for_output
) -> None:
    manager = rr_env["manager"]
    created = manager.create(name="raw-stream", shell=rr_env["shell"])
    initial = wait_for_output(manager, "raw-stream", b"RR_INITIAL_OUTPUT")
    assert initial.startswith(b"RR_INITIAL_OUTPUT")

    manager.send("raw-stream", "printf '\\033[31mRED\\033[0m\\rOVER\\n'")
    raw = wait_for_output(manager, "raw-stream", b"OVER")
    assert b"\x1b[31mRED\x1b[0m\rOVER" in raw
    assert created["transcript_end_cursor"] <= len(raw)


def test_external_human_input_is_visible_but_not_counted_as_rr_input(
    rr_env: Dict[str, Any], wait_for_output
) -> None:
    manager = rr_env["manager"]
    terminal = rr_env["terminal"]
    created = manager.create(name="human-collab", shell=rr_env["shell"])
    pane_id = created["tmux_pane_id"]
    assert manager.show("human-collab")["last_rr_input_at"] is None

    terminal._run(["send-keys", "-t", pane_id, "-l", "--", "printf 'HUMAN_VISIBLE\\n'"])
    terminal._run(["send-keys", "-t", pane_id, "C-m"])
    transcript = wait_for_output(manager, "human-collab", b"HUMAN_VISIBLE")

    assert b"printf 'HUMAN_VISIBLE" in transcript
    assert manager.show("human-collab")["last_rr_input_at"] is None
    assert created["tmux_session_name"] in manager.attach_argv("human-collab")


def test_named_ctrl_c_recovers_same_shell(rr_env: Dict[str, Any], wait_for_output) -> None:
    manager = rr_env["manager"]
    manager.create(name="keys", shell=rr_env["shell"])
    manager.send("keys", "printf 'SLEEP%s\\n' ING; sleep 30")
    wait_for_output(manager, "keys", b"SLEEPING")

    result = manager.key("keys", "C-c")
    assert set(result) == {"session_name", "read_from_cursor"}
    manager.send("keys", "printf 'RECOVER%s\\n' ED")
    transcript = wait_for_output(manager, "keys", b"RECOVERED")
    assert b"RECOVERED" in transcript


def test_shell_state_persists_across_independent_cli_style_calls(
    rr_env: Dict[str, Any], wait_for_output
) -> None:
    manager = rr_env["manager"]
    manager.create(name="persistent", shell=rr_env["shell"])
    manager.send("persistent", "export RR_PERSISTED=works")
    manager.send("persistent", "cd /tmp")
    manager.send("persistent", 'printf \'STATE=%s:%s\\n\' "$PWD" "$RR_PERSISTED"')

    transcript = wait_for_output(manager, "persistent", b"STATE=/tmp:works")
    assert b"STATE=/tmp:works" in transcript


def test_real_human_attach_input_enters_the_same_transcript(
    rr_env: Dict[str, Any], wait_for_output
) -> None:
    manager = rr_env["manager"]
    created = manager.create(name="attached-human", shell=rr_env["shell"])
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
    environment = os.environ.copy()
    environment["TERM"] = "xterm-256color"
    process = subprocess.Popen(
        manager.attach_argv("attached-human"),
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=environment,
        close_fds=True,
    )
    os.close(slave)
    try:
        deadline = time.monotonic() + 3
        attached = False
        while time.monotonic() < deadline:
            result = rr_env["terminal"]._run(
                [
                    "display-message",
                    "-p",
                    "-t",
                    created["tmux_session_name"],
                    "#{session_attached}",
                ],
                check=False,
            )
            if result.stdout.strip() == b"1":
                attached = True
                break
            time.sleep(0.02)
        assert attached
        os.write(master, b"printf 'ATTACHED_HUMAN\\n'\r")
        transcript = wait_for_output(manager, "attached-human", b"ATTACHED_HUMAN")
        assert b"printf 'ATTACHED_HUMAN" in transcript
        assert manager.show("attached-human")["last_rr_input_at"] is None
        os.write(master, b"\x02d")
        assert process.wait(timeout=3) == 0
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=3)
        os.close(master)


def test_startup_gate_can_recover_after_recorder_install(rr_env: Dict[str, Any]) -> None:
    terminal = rr_env["terminal"]
    session_dir = Path(rr_env["state_dir"]) / "startup-recovery"
    session_dir.mkdir(parents=True)
    transcript = session_dir / "transcript.log"
    transcript.touch()
    pending, release = terminal._startup_paths(session_dir)
    pending.touch()
    start_script = (
        f"while [ ! -e {shlex.quote(str(release))} ]; do sleep 0.01; done; "
        f"rm -f {shlex.quote(str(release))} {shlex.quote(str(pending))}; "
        f"exec {shlex.quote(rr_env['shell'])} -l"
    )
    created = terminal._run(
        [
            "new-session",
            "-d",
            "-P",
            "-F",
            "#{pane_id}",
            "-s",
            "rr-startup-recovery",
            shlex.join(["/bin/sh", "-c", start_script]),
        ]
    )
    pane_id = created.stdout.decode().strip()
    terminal._run(["pipe-pane", "-O", "-t", pane_id, f"cat >> {shlex.quote(str(transcript))}"])

    assert terminal.finish_startup(pane_id, session_dir)
    deadline = time.monotonic() + 3
    while b"RR_INITIAL_OUTPUT" not in transcript.read_bytes() and time.monotonic() < deadline:
        time.sleep(0.02)

    assert b"RR_INITIAL_OUTPUT" in transcript.read_bytes()
    assert not pending.exists()
    assert not release.exists()
