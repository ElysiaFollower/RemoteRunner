"""Session and command management for the mount-free Remote Runner core."""

import os
from typing import Any, Dict, Optional

from seed_runner.remote_backend import ParamikoRemoteBackend
from seed_runner.remote_machine import RemoteMachineManager, get_remote_machine_manager
from seed_runner.remote_state import (
    get_log_dir,
    list_session_states,
    load_session_state,
    remote_state_lock,
    save_session_state,
)
from seed_runner.utils import ensure_dir, generate_id, get_timestamp, write_file


class RemoteSessionManager:
    """Manage Remote Runner sessions without requiring mounts."""

    def __init__(
        self,
        machine_manager: Optional[RemoteMachineManager] = None,
        backend: Optional[ParamikoRemoteBackend] = None,
    ):
        self.machine_manager = machine_manager or get_remote_machine_manager()
        self.backend = backend or ParamikoRemoteBackend()

    def create(self, machine_id: str, cwd: Optional[str] = None) -> Dict[str, Any]:
        machine = self.machine_manager.get(machine_id)
        session_id = generate_id("sess")
        remote_cwd = cwd or machine.default_cwd
        log_dir = get_log_dir(session_id)
        ensure_dir(log_dir)
        session = {
            "session_id": session_id,
            "machine_id": machine_id,
            "cwd": remote_cwd,
            "status": "active",
            "busy": False,
            "active_command": None,
            "created_at": get_timestamp(),
            "last_command": None,
            "last_exit_code": None,
            "command_count": 0,
            "transfer_count": 0,
            "log_dir_local": log_dir,
            "commands": [],
        }
        with remote_state_lock():
            save_session_state(session)
        return self._public_session(session)

    def list(self) -> Dict[str, Any]:
        sessions = [self._public_session(session) for session in list_session_states()]
        return {"sessions": sessions, "summary": {"session_count": len(sessions)}}

    def show(self, session_id: str) -> Dict[str, Any]:
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
    ) -> Dict[str, Any]:
        reservation = self._reserve_command(session_id, command, cwd)
        machine = self.machine_manager.get(reservation["machine_id"])
        remote_cwd = reservation["cwd"]
        command_index = reservation["index"]
        log_filename = f"cmd_{command_index:03d}.log"
        log_file = os.path.join(reservation["log_dir_local"], log_filename)
        ensure_dir(reservation["log_dir_local"])

        try:
            result = self.backend.run(machine, remote_cwd, command, timeout=timeout)
            record = {
                "index": command_index,
                "command": command,
                "cwd": remote_cwd,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "started_at": result.started_at,
                "ended_at": result.ended_at,
                "duration_ms": result.duration_ms,
                "log_file_local": log_file,
                "status": "completed",
            }
            self._write_command_log(record)
        except Exception as exc:
            now = get_timestamp()
            record = {
                "index": command_index,
                "command": command,
                "cwd": remote_cwd,
                "exit_code": None,
                "stdout": "",
                "stderr": "",
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
            "machine_id": reservation["machine_id"],
            "cwd": remote_cwd,
            "command": command,
            "exit_code": record["exit_code"],
            "stdout": record["stdout"],
            "stderr": record["stderr"],
            "started_at": record["started_at"],
            "ended_at": record["ended_at"],
            "duration_ms": record["duration_ms"],
            "log_file_local": log_file,
        }

    def logs(self, session_id: str) -> Dict[str, Any]:
        session = load_session_state(session_id)
        return {
            "session_id": session_id,
            "logs": [
                {
                    "index": command["index"],
                    "command": command["command"],
                    "exit_code": command["exit_code"],
                    "started_at": command["started_at"],
                    "ended_at": command["ended_at"],
                    "log_file_local": command["log_file_local"],
                    "status": command.get("status", "completed"),
                }
                for command in session.get("commands", [])
            ],
        }

    def destroy(self, session_id: str) -> Dict[str, Any]:
        with remote_state_lock():
            session = load_session_state(session_id)
            if session.get("busy"):
                raise RuntimeError(f"Session '{session_id}' is busy")
            session["status"] = "destroyed"
            session["destroyed_at"] = get_timestamp()
            save_session_state(session)
        return {
            "session_id": session_id,
            "status": "destroyed",
            "destroyed_at": session["destroyed_at"],
            "logs_preserved": True,
            "logs_location": session["log_dir_local"],
        }

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
            if session.get("busy"):
                raise RuntimeError(f"Session '{session_id}' is busy")
            remote_cwd = cwd or session["cwd"]
            command_index = int(session.get("command_count", 0)) + 1
            session["busy"] = True
            session["active_command"] = {
                "index": command_index,
                "command": command,
                "cwd": remote_cwd,
                "reserved_at": get_timestamp(),
            }
            save_session_state(session)
        return {
            "index": command_index,
            "machine_id": session["machine_id"],
            "cwd": remote_cwd,
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
            session.setdefault("commands", []).append(record)
            save_session_state(session)

    def _write_command_log(self, record: Dict[str, Any]) -> None:
        lines = [
            f"[{record['started_at']}] $ {record['command']}",
            f"[cwd] {record['cwd']}",
        ]
        if record.get("stdout"):
            lines.append("[stdout]")
            lines.append(record["stdout"].rstrip())
        if record.get("stderr"):
            lines.append("[stderr]")
            lines.append(record["stderr"].rstrip())
        if record.get("error"):
            lines.append(f"[error] {record['error']}")
        lines.append(f"[{record['ended_at']}] $ exit_code: {record['exit_code']}")
        write_file(record["log_file_local"], "\n".join(lines) + "\n")
        os.chmod(record["log_file_local"], 0o600)

    def _public_session(self, session: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "session_id": session["session_id"],
            "machine_id": session["machine_id"],
            "cwd": session["cwd"],
            "status": session["status"],
            "busy": session.get("busy", False),
            "created_at": session["created_at"],
            "last_command": session.get("last_command"),
            "last_exit_code": session.get("last_exit_code"),
            "command_count": session.get("command_count", 0),
            "transfer_count": session.get("transfer_count", 0),
            "log_dir_local": session["log_dir_local"],
        }


def get_remote_session_manager() -> RemoteSessionManager:
    return RemoteSessionManager()
