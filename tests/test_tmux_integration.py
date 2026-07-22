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

import pytest

from remote_runner.errors import RemoteRunnerError, TmuxError


def create_external_tmux(rr_env: Dict[str, Any], name: str) -> str:
    terminal = rr_env["terminal"]
    created = terminal._run(
        [
            "new-session",
            "-d",
            "-P",
            "-F",
            "#{pane_id}",
            "-s",
            name,
            "-c",
            str(rr_env["state_dir"].parent),
            rr_env["shell"],
        ]
    )
    pane_id = created.stdout.decode().strip()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        visible = terminal._run(["capture-pane", "-p", "-t", pane_id], check=False)
        if b"RR_INITIAL_OUTPUT" in visible.stdout:
            return pane_id
        time.sleep(0.02)
    pytest.fail("external tmux shell did not become ready")


def test_recorder_starts_before_shell_and_preserves_raw_bytes(
    rr_env: Dict[str, Any], wait_for_output
) -> None:
    manager = rr_env["manager"]
    created = manager.create(name="raw-stream", shell=rr_env["shell"])
    initial = wait_for_output(manager, "raw-stream", b"RR_INITIAL_OUTPUT")
    assert initial.startswith(b"RR_INITIAL_OUTPUT")

    manager.send("raw-stream", "printf '\\033[31mRED\\033[0m\\rOVER\\n'")
    raw = wait_for_output(manager, "raw-stream", b"\x1b[31mRED\x1b[0m\rOVER")
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


def test_register_existing_tmux_captures_future_output_and_destroy_preserves_tmux(
    rr_env: Dict[str, Any], wait_for_output
) -> None:
    manager = rr_env["manager"]
    terminal = rr_env["terminal"]
    pane_id = create_external_tmux(rr_env, "external-shell")

    registered = manager.register(tmux_session_name="external-shell", name="adopted")

    assert registered["tmux_session_origin"] == "registered"
    assert registered["tmux_session_name"] == "external-shell"
    assert registered["tmux_pane_id"] == pane_id
    assert registered["local_shell_path"] is None
    assert manager.tail("adopted").output == b""
    assert terminal.managed_session_id(pane_id) == registered["session_id"]

    manager.send("adopted", "printf 'REGISTERED_VISIBLE\\n'")
    transcript = wait_for_output(manager, "adopted", b"REGISTERED_VISIBLE")
    assert b"printf 'REGISTERED_VISIBLE" in transcript

    destroyed = manager.destroy("adopted")
    assert destroyed["session_status"] == "destroyed"
    assert terminal.session_exists("external-shell")
    assert not terminal.recorder_exists(pane_id)
    assert terminal.managed_session_id(pane_id) is None

    repeated = manager.register(tmux_session_name="external-shell", name="adopted")
    assert repeated["session_id"] != registered["session_id"]


def test_register_rejects_ambiguous_or_already_observed_tmux_without_mutation(
    rr_env: Dict[str, Any],
) -> None:
    manager = rr_env["manager"]
    terminal = rr_env["terminal"]
    first_pane = create_external_tmux(rr_env, "many-panes")
    terminal._run(["split-window", "-d", "-t", first_pane, rr_env["shell"]])

    with pytest.raises(TmuxError) as multiple:
        manager.register(tmux_session_name="many-panes")
    assert multiple.value.code == "tmux_session_not_single_pane"

    piped_pane = create_external_tmux(rr_env, "already-piped")
    other_transcript = rr_env["state_dir"].parent / "other-transcript.log"
    terminal._run(["pipe-pane", "-O", "-t", piped_pane, f"cat >> {other_transcript}"])
    with pytest.raises(TmuxError) as piped:
        manager.register(tmux_session_name="already-piped")
    assert piped.value.code == "tmux_pane_already_piped"
    assert terminal.recorder_exists(piped_pane)

    marked_pane = create_external_tmux(rr_env, "already-marked")
    terminal._run(
        [
            "set-option",
            "-p",
            "-t",
            marked_pane,
            "@remote_runner_session_id",
            "sess_11111111111111111111111111111111",
        ]
    )
    with pytest.raises(TmuxError) as marked:
        manager.register(tmux_session_name="already-marked")
    assert marked.value.code == "tmux_pane_already_managed"
    assert not terminal.recorder_exists(marked_pane)

    with pytest.raises(TmuxError) as prefix:
        manager.register(tmux_session_name="already")
    assert prefix.value.code == "tmux_session_not_found"
    assert manager.list()["sessions"] == []


def test_registered_tmux_cannot_be_registered_twice_and_lost_recorder_is_safe(
    rr_env: Dict[str, Any],
) -> None:
    manager = rr_env["manager"]
    terminal = rr_env["terminal"]
    pane_id = create_external_tmux(rr_env, "one-owner")
    registered = manager.register(tmux_session_name="one-owner", name="first-owner")

    with pytest.raises(RemoteRunnerError) as duplicate:
        manager.register(tmux_session_name="one-owner", name="second-owner")
    assert duplicate.value.code == "tmux_pane_already_registered"

    terminal._run(["pipe-pane", "-t", pane_id])
    assert manager.show("first-owner")["session_status"] == "lost"
    assert manager.destroy("first-owner")["session_status"] == "destroyed"
    assert terminal.session_exists("one-owner")
    assert terminal.managed_session_id(pane_id) is None
    assert registered["session_id"] != ""


def test_registered_destroy_refuses_to_stop_a_recorder_after_marker_tampering(
    rr_env: Dict[str, Any],
) -> None:
    manager = rr_env["manager"]
    terminal = rr_env["terminal"]
    pane_id = create_external_tmux(rr_env, "marker-owner")
    registered = manager.register(tmux_session_name="marker-owner")
    terminal._run(
        [
            "set-option",
            "-p",
            "-t",
            pane_id,
            "@remote_runner_session_id",
            "sess_22222222222222222222222222222222",
        ]
    )

    assert manager.show("marker-owner")["session_status"] == "lost"
    with pytest.raises(TmuxError) as changed:
        manager.destroy("marker-owner")
    assert changed.value.code == "tmux_registration_ownership_changed"
    assert terminal.recorder_exists(pane_id)
    assert terminal.session_exists("marker-owner")

    terminal._run(
        [
            "set-option",
            "-p",
            "-t",
            pane_id,
            "@remote_runner_session_id",
            registered["session_id"],
        ]
    )
    assert manager.destroy("marker-owner")["session_status"] == "destroyed"
    assert not terminal.recorder_exists(pane_id)
