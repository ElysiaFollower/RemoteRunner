from pathlib import Path
from typing import Any, Dict

import pytest

from remote_runner.errors import RemoteRunnerError, TmuxError

STATE_KEYS = {
    "session_id",
    "session_name",
    "session_status",
    "tmux_session_name",
    "tmux_pane_id",
    "initial_cwd",
    "local_shell_path",
    "instance_name",
    "bootstrap_status",
    "created_at",
    "lost_at",
    "destroyed_at",
    "last_rr_input_at",
    "time_since_last_rr_input_ms",
    "last_output_at",
    "time_since_last_output_ms",
    "transcript_path",
    "transcript_end_cursor",
}


def test_create_exposes_only_terminal_state(rr_env: Dict[str, Any], wait_for_output) -> None:
    manager = rr_env["manager"]
    created = manager.create(name="clear-shell", shell=rr_env["shell"])
    wait_for_output(manager, "clear-shell", b"RR_INITIAL_OUTPUT")
    state = manager.show("clear-shell")

    assert set(state) == STATE_KEYS
    assert state["session_status"] == "active"
    assert state["session_name"] == "clear-shell"
    assert state["session_id"].startswith("sess_")
    assert state["tmux_session_name"].startswith("rr-clear-shell-")
    assert state["tmux_pane_id"].startswith("%")
    assert Path(state["transcript_path"]).is_absolute()
    assert state["transcript_end_cursor"] > 0
    assert state["last_output_at"] is not None
    assert created["session_id"] == state["session_id"]
    assert not list(Path(state["transcript_path"]).parent.glob("shell-start.*"))


def test_send_returns_only_name_and_anchor_and_never_persists_input(
    rr_env: Dict[str, Any], wait_for_output
) -> None:
    manager = rr_env["manager"]
    store = rr_env["store"]
    created = manager.create(name="secret-shell", shell=rr_env["shell"])
    secret = "RR_SECRET_VALUE_72e3"

    manager.send(
        "secret-shell",
        (
            "stty -echo; printf 'PASS%s:' WORD; read value; stty echo; "
            "printf 'SECRET_%s\\n' ACCEPTED"
        ),
    )
    wait_for_output(manager, "secret-shell", b"PASSWORD:")
    result = manager.send("secret-shell", secret)
    transcript = wait_for_output(manager, "secret-shell", b"SECRET_ACCEPTED")

    assert set(result) == {"session_name", "read_from_cursor"}
    assert result["session_name"] == "secret-shell"
    assert secret.encode() not in transcript
    state_text = store.session_state_path(created["session_id"]).read_text(encoding="utf-8")
    assert secret not in state_text
    assert manager.show("secret-shell")["last_rr_input_at"] is not None
    buffers = rr_env["terminal"]._run(
        ["list-buffers", "-F", "#{buffer_name}:#{buffer_sample}"], check=False
    )
    assert secret.encode() not in buffers.stdout


def test_multiline_send_and_unknown_key_fail_before_terminal_input(rr_env: Dict[str, Any]) -> None:
    manager = rr_env["manager"]
    manager.create(name="input-contract", shell=rr_env["shell"])
    before = manager.show("input-contract")["last_rr_input_at"]

    with pytest.raises(TmuxError) as multiline:
        manager.send("input-contract", "first\nsecond")
    assert multiline.value.code == "multiline_input"

    with pytest.raises(TmuxError) as key:
        manager.key("input-contract", "--not-a-key")
    assert key.value.code == "invalid_key"
    assert manager.show("input-contract")["last_rr_input_at"] == before


def test_read_and_tail_are_stateless_minimal_ranges(rr_env: Dict[str, Any]) -> None:
    manager = rr_env["manager"]
    store = rr_env["store"]
    created = manager.create(name="ranges", shell=rr_env["shell"])
    path = store.transcript_path(created["session_id"])
    payload = (b"0123456789abcdef" * 400000) + b"THE_END"
    with path.open("ab") as handle:
        handle.write(payload)

    first = manager.read("ranges", from_cursor=10, max_bytes=32)
    repeated = manager.read("ranges", from_cursor=10, max_bytes=32)
    tail = manager.tail("ranges", max_bytes=64)

    assert first == repeated
    assert len(first.output) == 32
    assert first.next_read_cursor == 42
    assert first.transcript_end_cursor == path.stat().st_size
    assert len(tail.output) == 64
    assert tail.output.endswith(b"THE_END")
    assert tail.output_start_cursor == tail.transcript_end_cursor - 64


def test_lost_session_preserves_transcript_then_destroy_releases_name(
    rr_env: Dict[str, Any], wait_for_output
) -> None:
    manager = rr_env["manager"]
    terminal = rr_env["terminal"]
    first = manager.create(name="reusable", shell=rr_env["shell"])
    manager.send("reusable", "printf 'OLD_HISTORY\\n'")
    wait_for_output(manager, "reusable", b"OLD_HISTORY")

    terminal.destroy(first["tmux_session_name"])
    lost = manager.show("reusable")
    assert lost["session_status"] == "lost"
    assert b"OLD_HISTORY" in manager.tail(first["session_id"]).output

    with pytest.raises(RemoteRunnerError) as send_error:
        manager.send("reusable", "printf 'MUST_NOT_RUN\\n'")
    assert send_error.value.code == "session_lost"

    destroyed = manager.destroy("reusable")
    assert destroyed["session_status"] == "destroyed"
    second = manager.create(name="reusable", shell=rr_env["shell"])
    assert second["session_id"] != first["session_id"]
    assert b"OLD_HISTORY" in manager.tail(first["session_id"]).output

    with pytest.raises(RemoteRunnerError) as confirmation:
        manager.purge(first["session_id"], confirm="wrong")
    assert confirmation.value.code == "purge_confirmation_required"
    assert manager.purge(first["session_id"], confirm=first["session_id"]) == {
        "session_id": first["session_id"]
    }


def test_active_session_name_is_unique(rr_env: Dict[str, Any]) -> None:
    manager = rr_env["manager"]
    manager.create(name="unique", shell=rr_env["shell"])

    with pytest.raises(RemoteRunnerError) as duplicate:
        manager.create(name="unique", shell=rr_env["shell"])

    assert duplicate.value.code == "session_name_in_use"
    assert len(manager.list()["sessions"]) == 1


def test_readable_name_with_dot_maps_to_safe_tmux_name(rr_env: Dict[str, Any]) -> None:
    manager = rr_env["manager"]

    created = manager.create(name="paper.eval", shell=rr_env["shell"])

    assert created["session_name"] == "paper.eval"
    assert "." not in created["tmux_session_name"]
    assert manager.show("paper.eval")["session_status"] == "active"


def test_missing_recorder_marks_session_lost_but_keeps_history(
    rr_env: Dict[str, Any], wait_for_output
) -> None:
    manager = rr_env["manager"]
    terminal = rr_env["terminal"]
    created = manager.create(name="recorder", shell=rr_env["shell"])
    manager.send("recorder", "printf 'RECORDED\\n'")
    wait_for_output(manager, "recorder", b"RECORDED")

    terminal._run(["pipe-pane", "-t", created["tmux_pane_id"]])

    assert manager.show("recorder")["session_status"] == "lost"
    assert b"RECORDED" in manager.tail(created["session_id"]).output
    assert manager.destroy("recorder")["session_status"] == "destroyed"


def test_starting_state_recovers_the_existing_tmux_pane(rr_env: Dict[str, Any]) -> None:
    manager = rr_env["manager"]
    store = rr_env["store"]
    created = manager.create(name="recover-create", shell=rr_env["shell"])
    stored = store.load_session(created["session_id"])
    stored["session_status"] = "starting"
    stored["tmux_pane_id"] = None
    store.save_session(stored)

    recovered = manager.show(created["session_id"])

    assert recovered["session_status"] == "active"
    assert recovered["tmux_pane_id"] == created["tmux_pane_id"]
    assert recovered["local_shell_path"] == str(Path(rr_env["shell"]).resolve())


def test_invalid_timeout_and_session_id_fail_without_creating_a_session(
    rr_env: Dict[str, Any],
) -> None:
    manager = rr_env["manager"]

    with pytest.raises(RemoteRunnerError) as timeout:
        manager.create(name="must-not-exist", shell=rr_env["shell"], bootstrap_timeout=0)
    assert timeout.value.code == "invalid_timeout"
    with pytest.raises(RemoteRunnerError) as non_finite:
        manager.create(
            name="still-must-not-exist", shell=rr_env["shell"], bootstrap_timeout=float("nan")
        )
    assert non_finite.value.code == "invalid_timeout"
    assert manager.list()["sessions"] == []

    with pytest.raises(RemoteRunnerError) as session_id:
        manager.purge("../../outside", confirm="../../outside")
    assert session_id.value.code == "invalid_session_id"
