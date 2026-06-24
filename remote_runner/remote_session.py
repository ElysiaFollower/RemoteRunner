"""Session and command management for the mount-free Remote Runner core."""

import os
import re
import time
from typing import Any, Dict, Optional

from remote_runner.remote_backend import DEFAULT_BACKGROUND_OUTPUT_LIMIT, ParamikoRemoteBackend
from remote_runner.remote_machine import RemoteMachineManager, get_remote_machine_manager
from remote_runner.remote_state import (
    get_log_dir,
    list_session_states,
    load_session_state,
    remote_state_lock,
    save_session_state,
)
from remote_runner.utils import (
    ensure_dir,
    generate_id,
    get_timestamp,
    parse_timestamp,
    read_file,
    write_file,
)


class RemoteSessionManager:
    """Manage Remote Runner sessions without requiring mounts."""

    SESSION_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")

    def __init__(
        self,
        machine_manager: Optional[RemoteMachineManager] = None,
        backend: Optional[ParamikoRemoteBackend] = None,
    ):
        self.machine_manager = machine_manager or get_remote_machine_manager()
        self.backend = backend or ParamikoRemoteBackend()

    def resolve_session_id(self, session_ref: str) -> str:
        """Resolve a session ID or unique readable session name to the canonical session ID."""
        try:
            return load_session_state(session_ref)["session_id"]
        except KeyError:
            pass

        current_matches = []
        historical_matches = []
        for session in list_session_states():
            if session.get("name") != session_ref:
                continue
            summary = f"{session['session_id']} ({session['machine_id']}, {session.get('status')})"
            if session.get("status") == "destroyed":
                historical_matches.append(summary)
            else:
                current_matches.append(summary)

        matches = current_matches or historical_matches
        if not matches:
            raise KeyError(f"Session '{session_ref}' not found")
        if len(matches) > 1:
            raise RuntimeError(
                f"Session name '{session_ref}' is ambiguous: " + ", ".join(matches)
            )
        return matches[0].split(" ", 1)[0]

    @staticmethod
    def _transcript_overlap(existing: str, captured: str) -> int:
        max_len = min(len(existing), len(captured))
        if max_len == 0:
            return 0

        pattern = captured[:max_len]
        text = existing[-max_len:]
        combined = pattern + "\0" + text
        prefix = [0] * len(combined)
        for index in range(1, len(combined)):
            length = prefix[index - 1]
            while length > 0 and combined[index] != combined[length]:
                length = prefix[length - 1]
            if combined[index] == combined[length]:
                length += 1
            prefix[index] = length
        return prefix[-1]

    @classmethod
    def _merge_transcript_capture(cls, existing: str, captured: str) -> str:
        if not captured:
            return existing
        if not existing:
            return captured
        if captured == existing or captured in existing or existing.endswith(captured):
            return existing
        if captured.startswith(existing):
            return captured

        overlap = cls._transcript_overlap(existing, captured)
        if overlap > 0:
            return existing + captured[overlap:]

        separator = "" if existing.endswith("\n") or captured.startswith("\n") else "\n"
        return existing + separator + captured

    def create(
        self,
        machine_id: str,
        cwd: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        machine = self.machine_manager.get(machine_id)
        session_id = generate_id("sess")
        remote_cwd = cwd or machine.default_cwd
        session_name = self._validate_session_name(name)
        if session_name:
            self._assert_session_name_available(
                name=session_name,
                machine_id=machine_id,
                exclude_session_id=session_id,
            )
        log_dir = get_log_dir(session_id)
        ensure_dir(log_dir)
        transcript_file = os.path.join(log_dir, "transcript.txt")
        created_at = get_timestamp()
        backend_record = self.backend.create_terminal(
            machine=machine,
            cwd=remote_cwd,
            terminal_id=session_id,
        )
        session = {
            "session_id": session_id,
            "name": session_name,
            "machine_id": machine_id,
            "cwd": remote_cwd,
            "backend": backend_record.get("backend", "tmux"),
            "status": "active",
            "busy": False,
            "active_command": None,
            "created_at": created_at,
            "updated_at": created_at,
            "destroyed_at": None,
            "last_command": None,
            "last_input": None,
            "last_exit_code": None,
            "command_count": 0,
            "transfer_count": 0,
            "log_dir_local": log_dir,
            "transcript_file_local": transcript_file,
            "transcript_cursor": 0,
            "commands": [],
            **backend_record,
        }
        write_file(transcript_file, "")
        os.chmod(transcript_file, 0o600)
        try:
            with remote_state_lock():
                if session_name:
                    self._assert_session_name_available(
                        name=session_name,
                        machine_id=machine_id,
                        exclude_session_id=session_id,
                    )
                save_session_state(session)
        except Exception:
            try:
                self.backend.destroy_terminal(machine, session)
            except Exception:
                pass
            raise
        return self._public_session(session)

    def list(self) -> Dict[str, Any]:
        sessions = [self._public_session(session) for session in list_session_states()]
        return {"sessions": sessions, "summary": {"session_count": len(sessions)}}

    def show(self, session_id: str) -> Dict[str, Any]:
        session_id = self.resolve_session_id(session_id)
        self._recover_stale_active_command(session_id)
        self._refresh_session_liveness(session_id)
        session = load_session_state(session_id)
        public = self._public_session(session)
        public["commands"] = session.get("commands", [])
        return public

    def exec(
        self,
        session_id: str,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 300,
        mode: str = "wait",
    ) -> Dict[str, Any]:
        session_id = self.resolve_session_id(session_id)
        self._recover_stale_active_command(session_id)
        self._refresh_session_liveness(session_id)
        if mode == "background":
            session = load_session_state(session_id)
            machine = self.machine_manager.get(session["machine_id"])
            if machine.backend == "windows-agent":
                raise RuntimeError("windows-agent backend does not yet support background mode")
            return self.start_background(session_id, command, cwd=cwd, timeout=timeout)
        if mode != "wait":
            raise ValueError("mode must be 'wait' or 'background'")

        reservation = self._reserve_command(session_id, command, cwd)
        machine = self.machine_manager.get(reservation["machine_id"])
        remote_cwd = reservation["cwd"]
        command_index = reservation["index"]
        command_id = reservation["command_id"]
        log_filename = f"cmd_{command_index:03d}.log"
        log_file = os.path.join(reservation["log_dir_local"], log_filename)
        ensure_dir(reservation["log_dir_local"])

        started_at = get_timestamp()
        try:
            backend_record = self.backend.start_session_command(
                machine=machine,
                session_record=load_session_state(session_id),
                command=command,
                command_id=command_id,
                cwd=remote_cwd,
                cwd_override=reservation["cwd_override"],
            )
            running_record = {
                "index": command_index,
                "command_id": command_id,
                "command": command,
                "cwd": remote_cwd,
                "mode": "wait",
                "exit_code": None,
                "stdout": "",
                "stderr": "",
                "stdout_truncated": False,
                "stderr_truncated": False,
                "started_at": started_at,
                "ended_at": None,
                "duration_ms": None,
                "log_file_local": log_file,
                "status": "running",
                **backend_record,
            }
            result = self.backend.wait_session_command(
                machine=machine,
                command_record=running_record,
                timeout=timeout,
            )
            ended_at = result.get("ended_at") or get_timestamp()
            started_at = result.get("started_at") or started_at
            status = result.get("status", "exited")
            record = {
                "index": command_index,
                "command_id": command_id,
                "command": command,
                "cwd": remote_cwd,
                "mode": "wait",
                "exit_code": result.get("exit_code"),
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
                "stdout_truncated": result.get("stdout_truncated", False),
                "stderr_truncated": result.get("stderr_truncated", False),
                "started_at": started_at,
                "ended_at": ended_at,
                "duration_ms": self._duration_ms(started_at, ended_at),
                "log_file_local": log_file,
                "status": "completed" if status == "exited" else status,
                **backend_record,
            }
            self._write_command_log(record)
        except Exception as exc:
            now = get_timestamp()
            record = {
                "index": command_index,
                "command_id": command_id,
                "command": command,
                "cwd": remote_cwd,
                "mode": "wait",
                "exit_code": None,
                "stdout": "",
                "stderr": "",
                "stdout_truncated": False,
                "stderr_truncated": False,
                "started_at": now,
                "ended_at": now,
                "duration_ms": 0,
                "log_file_local": log_file,
                "status": "failed",
                "error": str(exc),
            }
            self._write_command_log(record)
            self._persist_command(session_id, record)
            raise

        self._persist_command(session_id, record)
        return {
            "session_id": session_id,
            "command_id": command_id,
            "machine_id": reservation["machine_id"],
            "cwd": remote_cwd,
            "command": command,
            "status": record["status"],
            "exit_code": record["exit_code"],
            "stdout": record["stdout"],
            "stderr": record["stderr"],
            "stdout_truncated": record["stdout_truncated"],
            "stderr_truncated": record["stderr_truncated"],
            "started_at": record["started_at"],
            "ended_at": record["ended_at"],
            "duration_ms": record["duration_ms"],
            "log_file_local": log_file,
        }

    def start_background(
        self,
        session_id: str,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 15,
    ) -> Dict[str, Any]:
        session_id = self.resolve_session_id(session_id)
        reservation = self._reserve_command(session_id, command, cwd)
        machine = self.machine_manager.get(reservation["machine_id"])
        remote_cwd = reservation["cwd"]
        command_index = reservation["index"]
        command_id = reservation["command_id"]
        log_filename = f"cmd_{command_index:03d}.log"
        log_file = os.path.join(reservation["log_dir_local"], log_filename)
        ensure_dir(reservation["log_dir_local"])
        started_at = get_timestamp()

        try:
            backend_record = self.backend.start_session_command(
                machine=machine,
                session_record=load_session_state(session_id),
                command=command,
                command_id=command_id,
                cwd=remote_cwd,
                cwd_override=reservation["cwd_override"],
            )
            record = {
                "index": command_index,
                "command_id": command_id,
                "command": command,
                "cwd": remote_cwd,
                "mode": "background",
                "status": "running",
                "exit_code": None,
                "stdout": "",
                "stderr": "",
                "stdout_truncated": False,
                "stderr_truncated": False,
                "started_at": started_at,
                "ended_at": None,
                "duration_ms": None,
                "log_file_local": log_file,
                **backend_record,
            }
            self._write_command_log(record)
        except Exception as exc:
            now = get_timestamp()
            record = {
                "index": command_index,
                "command_id": command_id,
                "command": command,
                "cwd": remote_cwd,
                "mode": "background",
                "status": "failed",
                "exit_code": None,
                "stdout": "",
                "stderr": "",
                "stdout_truncated": False,
                "stderr_truncated": False,
                "started_at": started_at,
                "ended_at": now,
                "duration_ms": self._duration_ms(started_at, now),
                "log_file_local": log_file,
                "error": str(exc),
            }
            self._write_command_log(record)
            self._persist_command(session_id, record)
            raise

        self._persist_command(session_id, record)
        return self._public_command_result(session_id, reservation["machine_id"], record)

    def command_list(self, session_id: str) -> Dict[str, Any]:
        session_id = self.resolve_session_id(session_id)
        session = load_session_state(session_id)
        commands = [self._public_command_summary(command) for command in session.get("commands", [])]
        return {
            "session_id": session_id,
            "commands": commands,
            "summary": {"command_count": len(commands)},
        }

    def command_show(
        self,
        session_id: str,
        command_id: str,
        stdout_limit: int = DEFAULT_BACKGROUND_OUTPUT_LIMIT,
        stderr_limit: int = DEFAULT_BACKGROUND_OUTPUT_LIMIT,
    ) -> Dict[str, Any]:
        session_id = self.resolve_session_id(session_id)
        record = self._get_command_record(session_id, command_id)
        if record.get("mode") != "background":
            return self._public_command_result(
                session_id,
                self._session_machine_id(session_id),
                record,
            )

        machine = self.machine_manager.get(self._session_machine_id(session_id))
        try:
            if record.get("command_backend") == "tmux":
                update = self.backend.inspect_session_command(
                    machine=machine,
                    command_record=record,
                    stdout_limit=stdout_limit,
                    stderr_limit=stderr_limit,
                )
            else:
                update = self.backend.inspect_background(
                    machine=machine,
                    command_record=record,
                    stdout_limit=stdout_limit,
                    stderr_limit=stderr_limit,
                )
        except Exception:
            return self._public_command_result(
                session_id,
                self._session_machine_id(session_id),
                record,
            )
        updated = dict(record)
        updated.update(update)
        if updated.get("status") == "running" and record.get("command_backend") == "tmux":
            session = load_session_state(session_id)
            if not self._session_terminal_exists(machine, session):
                self._mark_session_lost(session_id)
                updated["status"] = "failed"
                updated["ended_at"] = updated.get("ended_at") or get_timestamp()
                updated["error"] = (
                    "remote tmux session is no longer running while command status is still running"
                )
        if updated.get("ended_at") and updated.get("duration_ms") is None:
            updated["duration_ms"] = self._duration_ms(updated["started_at"], updated["ended_at"])
        if updated.get("status") in {"exited", "failed", "stopped", "timed_out"}:
            updated["ended_at"] = updated.get("ended_at") or get_timestamp()
            updated["duration_ms"] = updated.get("duration_ms") or self._duration_ms(
                updated["started_at"],
                updated["ended_at"],
            )
        self._update_command_record(session_id, command_id, updated)
        self._write_command_log(updated)
        return self._public_command_result(
            session_id,
            self._session_machine_id(session_id),
            updated,
        )

    def command_wait(
        self,
        session_id: str,
        command_id: str,
        timeout: int = 30,
        poll_interval: float = 0.25,
        stdout_limit: int = DEFAULT_BACKGROUND_OUTPUT_LIMIT,
        stderr_limit: int = DEFAULT_BACKGROUND_OUTPUT_LIMIT,
    ) -> Dict[str, Any]:
        session_id = self.resolve_session_id(session_id)
        deadline = time.time() + max(0, timeout)
        while True:
            result = self.command_show(
                session_id,
                command_id,
                stdout_limit=stdout_limit,
                stderr_limit=stderr_limit,
            )
            if result["status"] != "running":
                result["wait_timed_out"] = False
                return result
            if time.time() >= deadline:
                result["wait_timed_out"] = True
                return result
            time.sleep(min(poll_interval, max(0, deadline - time.time())))

    def command_stop(self, session_id: str, command_id: str) -> Dict[str, Any]:
        session_id = self.resolve_session_id(session_id)
        record = self._get_command_record(session_id, command_id)
        machine_id = self._session_machine_id(session_id)
        if record.get("status") != "running":
            result = self._public_command_result(session_id, machine_id, record)
            result["stop_requested"] = False
            return result

        machine = self.machine_manager.get(machine_id)
        if record.get("command_backend") == "tmux":
            session = load_session_state(session_id)
            stop_result = self.backend.stop_session_command(machine, session, record)
        else:
            stop_result = self.backend.stop_background(machine, record)
        refreshed = self.command_show(session_id, command_id)
        refreshed["stop_requested"] = True
        refreshed.update(stop_result)
        return refreshed

    def send(self, session_id: str, input_text: str, enter: bool = True) -> Dict[str, Any]:
        session_id = self.resolve_session_id(session_id)
        session = load_session_state(session_id)
        if session.get("status") != "active":
            raise RuntimeError(f"Session '{session_id}' is not active")
        machine = self.machine_manager.get(session["machine_id"])
        send_result = self.backend.send_terminal_input(
            machine=machine,
            terminal_record=session,
            input_text=input_text,
            enter=enter,
        )
        session["last_input"] = input_text
        session["updated_at"] = get_timestamp()
        with remote_state_lock():
            save_session_state(session)
        result = self._public_session(session)
        result.update(send_result)
        result["enter"] = enter
        return result

    def read(
        self,
        session_id: str,
        since: Optional[int] = None,
        max_chars: Optional[int] = None,
    ) -> Dict[str, Any]:
        session_id = self.resolve_session_id(session_id)
        session = load_session_state(session_id)
        transcript_file = session["transcript_file_local"]
        captured_transcript: Optional[str] = None
        if session.get("status") == "active":
            machine = self.machine_manager.get(session["machine_id"])
            capture = self.backend.capture_terminal(machine=machine, terminal_record=session)
            captured_transcript = capture.get("transcript", "")
            status = capture.get("status") or session.get("status", "active")
        else:
            status = session.get("status", "destroyed")

        with remote_state_lock():
            session = load_session_state(session_id)
            transcript_file_exists = os.path.exists(transcript_file)
            if transcript_file_exists:
                existing_transcript = read_file(transcript_file)
            else:
                existing_transcript = ""
            if captured_transcript is None:
                transcript = existing_transcript
            else:
                transcript = self._merge_transcript_capture(
                    existing_transcript,
                    captured_transcript,
                )
            cursor = len(transcript)
            state_changed = (
                transcript != existing_transcript
                or status != session.get("status")
                or cursor != session.get("transcript_cursor", 0)
            )
            if state_changed:
                write_file(transcript_file, transcript)
                if not transcript_file_exists:
                    os.chmod(transcript_file, 0o600)
                session["status"] = status
                session["transcript_cursor"] = cursor
                session["updated_at"] = get_timestamp()
                save_session_state(session)

        cursor = len(transcript)
        start = max(0, since or 0)
        chunk = transcript[start:]
        truncated = False
        if max_chars is not None and max_chars >= 0 and len(chunk) > max_chars:
            chunk = chunk[:max_chars]
            truncated = True

        result = self._public_session(session)
        result.update(
            {
                "transcript": chunk,
                "cursor": cursor,
                "since": start,
                "transcript_truncated": truncated,
            }
        )
        return result

    def logs(self, session_id: str) -> Dict[str, Any]:
        session_id = self.resolve_session_id(session_id)
        session = load_session_state(session_id)
        return {
            "session_id": session_id,
            "logs": [
                {
                    "index": command["index"],
                    "command_id": command.get("command_id"),
                    "command": command["command"],
                    "mode": command.get("mode", "wait"),
                    "exit_code": command.get("exit_code"),
                    "started_at": command["started_at"],
                    "ended_at": command.get("ended_at"),
                    "log_file_local": command["log_file_local"],
                    "status": command.get("status", "completed"),
                }
                for command in session.get("commands", [])
            ],
        }

    def destroy(self, session_id: str) -> Dict[str, Any]:
        session_id = self.resolve_session_id(session_id)
        self._recover_stale_active_command(session_id)
        self._refresh_session_liveness(session_id)
        session = load_session_state(session_id)
        if session.get("busy"):
            raise RuntimeError(f"Session '{session_id}' is busy")
        running_commands = [
            command.get("command_id") or str(command.get("index"))
            for command in session.get("commands", [])
            if command.get("status") == "running"
        ]
        if running_commands:
            raise RuntimeError(
                f"Session '{session_id}' has running background commands: "
                + ", ".join(running_commands)
            )

        capture_error = None
        destroy_result: Dict[str, Any] = {"destroy_result": "already_destroyed"}
        if session.get("status") == "active":
            try:
                self.read(session_id)
            except Exception as exc:
                capture_error = str(exc)
            machine = self.machine_manager.get(session["machine_id"])
            destroy_result = self.backend.destroy_terminal(machine, session)

        with remote_state_lock():
            session = load_session_state(session_id)
            session["status"] = "destroyed"
            session["destroyed_at"] = get_timestamp()
            session["updated_at"] = session["destroyed_at"]
            save_session_state(session)
        result = {
            "session_id": session_id,
            "status": "destroyed",
            "destroyed_at": session["destroyed_at"],
            "logs_preserved": True,
            "logs_location": session["log_dir_local"],
            "transcript_file_local": session.get("transcript_file_local"),
            **destroy_result,
        }
        if capture_error:
            result["transcript_capture_error"] = capture_error
        return result

    def _session_terminal_exists(self, machine: Any, session: Dict[str, Any]) -> bool:
        try:
            return self.backend.terminal_exists(machine, session)
        except Exception:
            return True

    def _validate_session_name(self, name: Optional[str]) -> Optional[str]:
        if name is None:
            return None
        if not isinstance(name, str) or not name:
            raise ValueError("session name must be a non-empty string")
        if name.startswith("sess_"):
            raise ValueError("session name must not start with 'sess_'")
        if not self.SESSION_NAME_PATTERN.fullmatch(name):
            raise ValueError(
                "session name may only contain letters, digits, '.', '_', and '-'"
            )
        return name

    def _assert_session_name_available(
        self,
        name: str,
        machine_id: str,
        exclude_session_id: Optional[str] = None,
    ) -> None:
        for session in list_session_states():
            if session["session_id"] == exclude_session_id:
                continue
            if session.get("machine_id") != machine_id:
                continue
            if session.get("name") != name:
                continue
            if session.get("status") == "destroyed":
                continue
            raise RuntimeError(
                f"Session name '{name}' is already used by active session "
                f"'{session['session_id']}' on machine '{machine_id}'"
            )

    def _recover_stale_active_command(self, session_id: str) -> None:
        session = load_session_state(session_id)
        active_command = session.get("active_command")
        if (
            session.get("status") != "active"
            or not session.get("busy")
            or not active_command
        ):
            return

        machine = self.machine_manager.get(session["machine_id"])
        if self._session_terminal_exists(machine, session):
            return

        now = get_timestamp()
        started_at = active_command.get("reserved_at") or now
        command_index = int(active_command.get("index") or session.get("command_count", 0) + 1)
        log_file = os.path.join(session["log_dir_local"], f"cmd_{command_index:03d}.log")
        record = {
            "index": command_index,
            "command_id": active_command.get("command_id"),
            "command": active_command.get("command", ""),
            "cwd": active_command.get("cwd") or session["cwd"],
            "mode": "unknown",
            "status": "failed",
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
            "started_at": started_at,
            "ended_at": now,
            "duration_ms": self._duration_ms(started_at, now),
            "log_file_local": log_file,
            "error": "remote tmux session disappeared while command was reserved",
        }
        self._write_command_log(record)
        with remote_state_lock():
            session = load_session_state(session_id)
            if not session.get("busy") or not session.get("active_command"):
                return
            session.setdefault("commands", []).append(record)
            session["command_count"] = max(int(session.get("command_count", 0)), command_index)
            session["last_command"] = record["command"]
            session["last_exit_code"] = None
            session["busy"] = False
            session["active_command"] = None
            session["updated_at"] = now
            save_session_state(session)

    def _refresh_session_liveness(self, session_id: str) -> None:
        session = load_session_state(session_id)
        if session.get("status") != "active" or session.get("busy"):
            return
        machine = self.machine_manager.get(session["machine_id"])
        if self._session_terminal_exists(machine, session):
            return
        self._mark_session_lost(session_id)

    def _mark_session_lost(self, session_id: str) -> None:
        now = get_timestamp()
        with remote_state_lock():
            session = load_session_state(session_id)
            if session.get("status") == "active" and not session.get("busy"):
                session["status"] = "lost"
                session["updated_at"] = now
                save_session_state(session)

    def _reserve_command(
        self,
        session_id: str,
        command: str,
        cwd: Optional[str],
    ) -> Dict[str, Any]:
        with remote_state_lock():
            session = load_session_state(session_id)
            if session.get("status") == "destroyed":
                raise RuntimeError(f"Session '{session_id}' has been destroyed")
            if session.get("status") != "active":
                raise RuntimeError(f"Session '{session_id}' is not active")
            if session.get("busy"):
                raise RuntimeError(f"Session '{session_id}' is busy")
            running_commands = [
                command.get("command_id") or str(command.get("index"))
                for command in session.get("commands", [])
                if command.get("status") == "running"
            ]
            if running_commands:
                raise RuntimeError(
                    f"Session '{session_id}' has running commands: "
                    + ", ".join(running_commands)
                )
            remote_cwd = cwd or session["cwd"]
            command_index = int(session.get("command_count", 0)) + 1
            command_id = generate_id("cmd")
            session["busy"] = True
            session["active_command"] = {
                "index": command_index,
                "command_id": command_id,
                "command": command,
                "cwd": remote_cwd,
                "reserved_at": get_timestamp(),
            }
            save_session_state(session)
        return {
            "index": command_index,
            "command_id": command_id,
            "machine_id": session["machine_id"],
            "cwd": remote_cwd,
            "cwd_override": cwd is not None,
            "log_dir_local": session["log_dir_local"],
        }

    def _persist_command(self, session_id: str, record: Dict[str, Any]) -> None:
        with remote_state_lock():
            session = load_session_state(session_id)
            session["command_count"] = record["index"]
            session["last_command"] = record["command"]
            session["last_exit_code"] = record["exit_code"]
            session["busy"] = False
            session["active_command"] = None
            session["updated_at"] = get_timestamp()
            session.setdefault("commands", []).append(record)
            save_session_state(session)

    def _write_command_log(self, record: Dict[str, Any]) -> None:
        lines = [
            f"[{record['started_at']}] $ {record['command']}",
            f"[cwd] {record['cwd']}",
            f"[command_id] {record.get('command_id')}",
            f"[mode] {record.get('mode', 'wait')}",
            f"[status] {record.get('status', 'completed')}",
        ]
        if record.get("stdout"):
            lines.append("[stdout]")
            lines.append(record["stdout"].rstrip())
            if record.get("stdout_truncated"):
                lines.append("[stdout_truncated] true")
        if record.get("stderr"):
            lines.append("[stderr]")
            lines.append(record["stderr"].rstrip())
            if record.get("stderr_truncated"):
                lines.append("[stderr_truncated] true")
        if record.get("error"):
            lines.append(f"[error] {record['error']}")
        ended_at = record.get("ended_at") or get_timestamp()
        lines.append(f"[{ended_at}] $ exit_code: {record.get('exit_code')}")
        write_file(record["log_file_local"], "\n".join(lines) + "\n")
        os.chmod(record["log_file_local"], 0o600)

    def _session_machine_id(self, session_id: str) -> str:
        return load_session_state(session_id)["machine_id"]

    def _get_command_record(self, session_id: str, command_id: str) -> Dict[str, Any]:
        session = load_session_state(session_id)
        for command in session.get("commands", []):
            if command.get("command_id") == command_id:
                return dict(command)
        raise KeyError(f"Command '{command_id}' not found in session '{session_id}'")

    def _update_command_record(
        self,
        session_id: str,
        command_id: str,
        updated: Dict[str, Any],
    ) -> None:
        with remote_state_lock():
            session = load_session_state(session_id)
            commands = session.setdefault("commands", [])
            for index, command in enumerate(commands):
                if command.get("command_id") == command_id:
                    commands[index] = updated
                    session["last_command"] = updated["command"]
                    session["last_exit_code"] = updated.get("exit_code")
                    session["updated_at"] = get_timestamp()
                    save_session_state(session)
                    return
        raise KeyError(f"Command '{command_id}' not found in session '{session_id}'")

    def _duration_ms(self, started_at: str, ended_at: Optional[str]) -> Optional[int]:
        if not ended_at:
            return None
        try:
            return int((parse_timestamp(ended_at) - parse_timestamp(started_at)).total_seconds() * 1000)
        except Exception:
            return None

    def _public_command_summary(self, record: Dict[str, Any]) -> Dict[str, Any]:
        result = {
            "index": record["index"],
            "command_id": record.get("command_id"),
            "command": record["command"],
            "cwd": record["cwd"],
            "mode": record.get("mode", "wait"),
            "status": record.get("status", "completed"),
            "exit_code": record.get("exit_code"),
            "started_at": record["started_at"],
            "ended_at": record.get("ended_at"),
            "duration_ms": record.get("duration_ms"),
            "log_file_local": record["log_file_local"],
        }
        if record.get("error"):
            result["error"] = record["error"]
        return result

    def _public_command_result(
        self,
        session_id: str,
        machine_id: str,
        record: Dict[str, Any],
    ) -> Dict[str, Any]:
        result = {
            "session_id": session_id,
            "command_id": record.get("command_id"),
            "machine_id": machine_id,
            "cwd": record["cwd"],
            "command": record["command"],
            "mode": record.get("mode", "wait"),
            "status": record.get("status", "completed"),
            "exit_code": record.get("exit_code"),
            "stdout": record.get("stdout", ""),
            "stderr": record.get("stderr", ""),
            "stdout_truncated": record.get("stdout_truncated", False),
            "stderr_truncated": record.get("stderr_truncated", False),
            "started_at": record["started_at"],
            "ended_at": record.get("ended_at"),
            "duration_ms": record.get("duration_ms"),
            "log_file_local": record["log_file_local"],
            "remote_state_dir": record.get("remote_state_dir"),
            "remote_pid": record.get("remote_pid"),
        }
        if record.get("error"):
            result["error"] = record["error"]
        for key in (
            "remote_stdout_file",
            "remote_stderr_file",
            "remote_status_file",
            "remote_pid_file",
            "remote_exit_code_file",
            "remote_started_at_file",
            "remote_ended_at_file",
            "remote_worker_file",
            "remote_wrapper_file",
            "command_backend",
        ):
            if key in record:
                result[key] = record[key]
        return result

    def _public_session(self, session: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "session_id": session["session_id"],
            "name": session.get("name"),
            "machine_id": session["machine_id"],
            "cwd": session["cwd"],
            "status": session["status"],
            "busy": session.get("busy", False),
            "backend": session.get("backend"),
            "created_at": session["created_at"],
            "updated_at": session.get("updated_at"),
            "destroyed_at": session.get("destroyed_at"),
            "last_command": session.get("last_command"),
            "last_input": session.get("last_input"),
            "last_exit_code": session.get("last_exit_code"),
            "command_count": session.get("command_count", 0),
            "transfer_count": session.get("transfer_count", 0),
            "log_dir_local": session["log_dir_local"],
            "transcript_cursor": session.get("transcript_cursor", 0),
            "transcript_file_local": session.get("transcript_file_local"),
            "remote_backend_name": session.get("remote_terminal_name"),
        }


def get_remote_session_manager() -> RemoteSessionManager:
    return RemoteSessionManager()
