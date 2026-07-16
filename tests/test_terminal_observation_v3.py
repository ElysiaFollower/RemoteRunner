from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from remote_runner.cli import build_parser, main as remote_cli_main
from remote_runner.remote_machine import RemoteMachineManager
from remote_runner.remote_session import RemoteSessionManager
from remote_runner.remote_state import load_session_state, remote_state_lock, save_session_state

SEND_KEYS = {
    "session_id",
    "status",
    "input_sent",
    "input",
    "enter",
    "last_input_at",
    "last_output_at",
    "output_idle_ms",
    "start_cursor",
    "last_cursor",
}

READ_KEYS = {
    "session_id",
    "status",
    "transcript",
    "last_input_at",
    "last_output_at",
    "output_idle_ms",
    "start_cursor",
    "next_cursor",
    "last_cursor",
    "since",
    "cursor",
    "transcript_truncated",
}

INTERRUPT_KEYS = {
    "session_id",
    "status",
    "interrupt_sent",
    "last_input_at",
    "last_output_at",
    "output_idle_ms",
    "start_cursor",
    "last_cursor",
}


class ObservationBackend:
    def __init__(self):
        self.status = "active"

    def create_terminal(
        self,
        machine,
        cwd,
        terminal_id,
        terminal_name=None,
        transcript_file_local=None,
        width=160,
        height=48,
        history_limit=10000,
    ):
        return {
            "backend": "openssh-pty",
            "local_tmux_session": f"rr_{terminal_name or terminal_id}",
            "remote_terminal_name": f"rr_{terminal_name or terminal_id}",
            "local_transcript_file": transcript_file_local,
            "transcript_mode": "append-only",
        }

    def capture_terminal(self, machine, terminal_record):
        return {"status": self.status}

    def terminal_exists(self, machine, terminal_record):
        return True

    def send_terminal_input(self, machine, terminal_record, input_text, enter=True):
        return {"input_sent": True}

    def interrupt_terminal(self, machine, terminal_record):
        return {"interrupt_sent": True}

    def destroy_terminal(self, machine, terminal_record):
        return {"destroy_result": "destroyed"}


@pytest.fixture
def observation_manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    state_dir = tmp_path / "state"
    monkeypatch.setenv("REMOTE_RUNNER_STATE_DIR", str(state_dir))
    machines = RemoteMachineManager()
    machines.add(
        machine_id="local-observation",
        auth_type="manual",
        backend="openssh-pty",
        ssh_alias="unused-test-alias",
        platform="linux",
        shell="bash",
        default_cwd="~",
    )
    manager = RemoteSessionManager(
        machine_manager=machines,
        backend=ObservationBackend(),
    )
    created = manager.create("local-observation", name="observation")
    return manager, created


def _transcript_path(created: dict[str, object]) -> Path:
    return Path(str(created["transcript_file_local"]))


def test_send_returns_compact_acknowledgement_with_observation_metadata(
    observation_manager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, created = observation_manager
    transcript = _transcript_path(created)
    transcript.write_text("demo$ ", encoding="utf-8")
    monkeypatch.setattr(
        "remote_runner.remote_session.get_timestamp",
        lambda: "2026-07-16T10:00:00Z",
    )

    sent = manager.send(created["session_id"], "pwd")

    assert set(sent) == SEND_KEYS
    assert sent["input_sent"] is True
    assert sent["input"] == "pwd"
    assert sent["last_input_at"] == "2026-07-16T10:00:00Z"
    assert sent["start_cursor"] == len("demo$ ".encode("utf-8"))
    assert sent["last_cursor"] == sent["start_cursor"]
    assert "log_dir_local" not in sent
    assert "machine_id" not in sent


def test_read_uses_utf8_byte_cursors_and_never_skips_bounded_output(
    observation_manager,
) -> None:
    manager, created = observation_manager
    transcript = _transcript_path(created)
    content = "demo$ printf λ\nλ\ndemo$ "
    transcript.write_text(content, encoding="utf-8")

    first = manager.read(created["session_id"], since=0, max_bytes=17)
    second = manager.read(created["session_id"], since=first["next_cursor"])

    assert set(first) == READ_KEYS
    assert first["start_cursor"] == 0
    assert first["next_cursor"] == len(first["transcript"].encode("utf-8"))
    assert first["next_cursor"] < first["last_cursor"]
    assert first["transcript_truncated"] is True
    assert first["transcript"] + second["transcript"] == content
    assert second["next_cursor"] == second["last_cursor"]


def test_bounded_read_stops_before_split_utf8_character(observation_manager) -> None:
    manager, created = observation_manager
    transcript = _transcript_path(created)
    transcript.write_text("aλb", encoding="utf-8")

    first = manager.read(created["session_id"], since=0, max_bytes=2)
    second = manager.read(created["session_id"], since=first["next_cursor"])

    assert first["transcript"] == "a"
    assert first["next_cursor"] == 1
    assert second["transcript"] == "λb"


def test_legacy_character_limit_keeps_byte_cursor_for_invalid_utf8(
    observation_manager,
) -> None:
    manager, created = observation_manager
    transcript = _transcript_path(created)
    transcript.write_bytes(b"a\xffb")

    first = manager.read(created["session_id"], since=0, max_chars=2)
    second = manager.read(created["session_id"], since=first["next_cursor"])

    assert first["transcript"] == "a�"
    assert first["next_cursor"] == 2
    assert second["transcript"] == "b"


def test_transcript_append_preserves_crlf_and_utf8_bytes(observation_manager) -> None:
    manager, created = observation_manager
    transcript = _transcript_path(created)

    manager._append_transcript_text(str(transcript), "line\r\nλ\r\n")

    assert transcript.read_bytes() == "line\r\nλ\r\n".encode("utf-8")


def test_tail_is_explicit_bounded_observation_without_full_file_read(
    observation_manager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, created = observation_manager
    transcript = _transcript_path(created)
    transcript.write_bytes(b"old-output\n" * 500_000 + b"epoch=999\ndemo$ ")
    monkeypatch.setattr(
        manager,
        "_read_transcript_text",
        lambda path: (_ for _ in ()).throw(AssertionError("full transcript read")),
    )

    tailed = manager.tail(created["session_id"], tail_bytes=64)

    assert set(tailed) == READ_KEYS | {"history_before"}
    assert tailed["transcript"].endswith("epoch=999\ndemo$ ")
    assert len(tailed["transcript"].encode("utf-8")) <= 64
    assert tailed["start_cursor"] > 0
    assert tailed["next_cursor"] == tailed["last_cursor"]
    assert tailed["history_before"] is True


def test_read_rejects_cursor_beyond_append_only_tail(observation_manager) -> None:
    manager, created = observation_manager
    _transcript_path(created).write_text("prompt$ ", encoding="utf-8")

    with pytest.raises(ValueError, match="beyond transcript tail"):
        manager.read(created["session_id"], since=999)


def test_read_rejects_cursor_inside_utf8_character(observation_manager) -> None:
    manager, created = observation_manager
    _transcript_path(created).write_text("λ", encoding="utf-8")

    with pytest.raises(ValueError, match="UTF-8 character boundary"):
        manager.read(created["session_id"], since=1)


def test_empty_and_zero_byte_tail_have_exact_empty_range(observation_manager) -> None:
    manager, created = observation_manager

    observed = manager.tail(created["session_id"], tail_bytes=0)

    assert observed["transcript"] == ""
    assert observed["start_cursor"] == 0
    assert observed["next_cursor"] == 0
    assert observed["last_cursor"] == 0
    assert observed["history_before"] is False


@pytest.mark.parametrize("status", ["lost", "destroyed"])
def test_terminal_history_remains_readable_after_terminal_stops(
    observation_manager,
    status: str,
) -> None:
    manager, created = observation_manager
    _transcript_path(created).write_text("final output\nprompt$ ", encoding="utf-8")
    if status == "lost":
        manager.backend.status = "lost"
    else:
        with remote_state_lock():
            state = load_session_state(created["session_id"])
            state["status"] = "destroyed"
            save_session_state(state)

    observed = manager.tail(created["session_id"], tail_bytes=128)

    assert observed["status"] == status
    assert observed["transcript"] == "final output\nprompt$ "


def test_negative_terminal_read_limits_are_rejected(observation_manager) -> None:
    manager, created = observation_manager

    with pytest.raises(ValueError, match="max_bytes"):
        manager.read(created["session_id"], max_bytes=-1)
    with pytest.raises(ValueError, match="tail_bytes"):
        manager.tail(created["session_id"], tail_bytes=-1)


def test_interrupt_returns_compact_terminal_acknowledgement(observation_manager) -> None:
    manager, created = observation_manager
    _transcript_path(created).write_text("running\n", encoding="utf-8")

    interrupted = manager.interrupt(created["session_id"])

    assert set(interrupted) == INTERRUPT_KEYS
    assert interrupted["interrupt_sent"] is True
    assert "machine_id" not in interrupted


def test_last_output_time_and_idle_are_observation_metadata(observation_manager) -> None:
    manager, created = observation_manager
    transcript = _transcript_path(created)
    transcript.write_text("prompt$ ", encoding="utf-8")
    os.utime(transcript, (1_700_000_000, 1_700_000_000))

    observed = manager.tail(created["session_id"], tail_bytes=32)

    assert observed["last_output_at"] is not None
    assert observed["output_idle_ms"] is not None
    assert observed["output_idle_ms"] >= 0


def test_legacy_session_cursor_is_migrated_to_utf8_bytes(observation_manager) -> None:
    manager, created = observation_manager
    transcript = _transcript_path(created)
    transcript.write_text("λ prompt$ ", encoding="utf-8")
    with remote_state_lock():
        state = load_session_state(created["session_id"])
        state.pop("transcript_cursor_unit", None)
        state["transcript_cursor"] = len("λ prompt$ ")
        save_session_state(state)

    observed = manager.tail(created["session_id"], tail_bytes=64)
    migrated = load_session_state(created["session_id"])

    assert observed["last_cursor"] == len("λ prompt$ ".encode("utf-8"))
    assert migrated["transcript_cursor"] == observed["last_cursor"]
    assert migrated["transcript_cursor_unit"] == "utf8-bytes-v1"


def test_cli_exposes_tail_and_plain_terminal_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = {
        "session_id": "sess_demo",
        "status": "active",
        "transcript": "epoch=3\nprompt$ ",
        "last_input_at": None,
        "last_output_at": None,
        "output_idle_ms": None,
        "start_cursor": 10,
        "next_cursor": 26,
        "last_cursor": 26,
        "transcript_truncated": False,
        "history_before": True,
    }

    class StubManager:
        def tail(self, session_id, tail_bytes):
            assert session_id == "demo"
            assert tail_bytes == 4096
            return payload

    monkeypatch.setattr("remote_runner.cli.get_remote_session_manager", StubManager)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "remote-runner",
            "session",
            "tail",
            "--session",
            "demo",
            "--bytes",
            "4096",
            "--plain",
        ],
    )

    remote_cli_main()

    assert capsys.readouterr().out == "epoch=3\nprompt$ "


def test_cli_read_accepts_safe_byte_limit() -> None:
    args = build_parser().parse_args(
        [
            "session",
            "read",
            "--session",
            "demo",
            "--since",
            "120",
            "--max-bytes",
            "4096",
            "--json",
        ]
    )

    assert args.since == 120
    assert args.max_bytes == 4096


def test_canonical_skill_requires_human_terminal_discipline() -> None:
    skill = (Path(__file__).parents[1] / "SKILL.md").read_text(encoding="utf-8")

    assert "single-operator" in skill
    assert "shell prompt" in skill
    assert "one independent session per agent" in skill
    assert "interactive foreground program" in skill
    assert "session tail" in skill
