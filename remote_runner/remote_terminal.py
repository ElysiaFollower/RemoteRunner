"""Persistent terminal session management for Remote Runner."""

import os
from typing import Any, Dict, Optional

from remote_runner.remote_backend import ParamikoRemoteBackend
from remote_runner.remote_machine import RemoteMachineManager, get_remote_machine_manager
from remote_runner.remote_state import (
    get_terminal_log_dir,
    list_terminal_states,
    load_terminal_state,
    remote_state_lock,
    save_terminal_state,
)
from remote_runner.utils import ensure_dir, generate_id, get_timestamp, read_file, write_file


class RemoteTerminalManager:
    """Manage durable terminal-like remote shell sessions."""

    def __init__(
        self,
        machine_manager: Optional[RemoteMachineManager] = None,
        backend: Optional[ParamikoRemoteBackend] = None,
    ):
        self.machine_manager = machine_manager or get_remote_machine_manager()
        self.backend = backend or ParamikoRemoteBackend()

    def create(
        self,
        machine_id: str,
        cwd: Optional[str] = None,
        backend: str = "tmux",
        width: int = 120,
        height: int = 40,
    ) -> Dict[str, Any]:
        if backend != "tmux":
            raise ValueError("terminal backend must be 'tmux'")
        machine = self.machine_manager.get(machine_id)
        terminal_id = generate_id("term")
        remote_cwd = cwd or machine.default_cwd
        log_dir = get_terminal_log_dir(terminal_id)
        ensure_dir(log_dir)
        transcript_file = os.path.join(log_dir, "transcript.txt")
        created_at = get_timestamp()
        backend_record = self.backend.create_terminal(
            machine=machine,
            cwd=remote_cwd,
            terminal_id=terminal_id,
            width=width,
            height=height,
        )
        terminal = {
            "terminal_id": terminal_id,
            "machine_id": machine_id,
            "cwd": remote_cwd,
            "backend": backend_record.get("backend", backend),
            "status": "active",
            "created_at": created_at,
            "updated_at": created_at,
            "destroyed_at": None,
            "last_input": None,
            "transcript_cursor": 0,
            "transcript_file_local": transcript_file,
            "log_dir_local": log_dir,
            **backend_record,
        }
        write_file(transcript_file, "")
        os.chmod(transcript_file, 0o600)
        with remote_state_lock():
            save_terminal_state(terminal)
        return self._public_terminal(terminal)

    def list(self) -> Dict[str, Any]:
        terminals = [self._public_terminal(terminal) for terminal in list_terminal_states()]
        return {"terminals": terminals, "summary": {"terminal_count": len(terminals)}}

    def show(self, terminal_id: str) -> Dict[str, Any]:
        return self._public_terminal(load_terminal_state(terminal_id))

    def send(self, terminal_id: str, input_text: str, enter: bool = True) -> Dict[str, Any]:
        terminal = load_terminal_state(terminal_id)
        if terminal.get("status") != "active":
            raise RuntimeError(f"Terminal '{terminal_id}' is not active")
        machine = self.machine_manager.get(terminal["machine_id"])
        send_result = self.backend.send_terminal_input(
            machine=machine,
            terminal_record=terminal,
            input_text=input_text,
            enter=enter,
        )
        terminal["last_input"] = input_text
        terminal["updated_at"] = get_timestamp()
        with remote_state_lock():
            save_terminal_state(terminal)
        result = self._public_terminal(terminal)
        result.update(send_result)
        result["enter"] = enter
        return result

    def read(
        self,
        terminal_id: str,
        since: Optional[int] = None,
        max_chars: Optional[int] = None,
    ) -> Dict[str, Any]:
        terminal = load_terminal_state(terminal_id)
        if terminal.get("status") == "active":
            machine = self.machine_manager.get(terminal["machine_id"])
            capture = self.backend.capture_terminal(machine=machine, terminal_record=terminal)
            transcript = capture.get("transcript", "")
            status = capture.get("status") or terminal.get("status", "active")
        else:
            transcript = read_file(terminal["transcript_file_local"])
            status = terminal.get("status", "destroyed")
        cursor = len(transcript)
        start = max(0, since or 0)
        chunk = transcript[start:]
        truncated = False
        if max_chars is not None and max_chars >= 0 and len(chunk) > max_chars:
            chunk = chunk[:max_chars]
            truncated = True

        terminal["status"] = status
        terminal["transcript_cursor"] = cursor
        terminal["updated_at"] = get_timestamp()
        write_file(terminal["transcript_file_local"], transcript)
        os.chmod(terminal["transcript_file_local"], 0o600)
        with remote_state_lock():
            save_terminal_state(terminal)

        result = self._public_terminal(terminal)
        result.update(
            {
                "transcript": chunk,
                "cursor": cursor,
                "since": start,
                "transcript_truncated": truncated,
            }
        )
        return result

    def destroy(self, terminal_id: str) -> Dict[str, Any]:
        terminal = load_terminal_state(terminal_id)
        destroy_result: Dict[str, Any] = {"destroy_result": "already_destroyed"}
        if terminal.get("status") == "active":
            machine = self.machine_manager.get(terminal["machine_id"])
            destroy_result = self.backend.destroy_terminal(
                machine=machine,
                terminal_record=terminal,
            )
        terminal["status"] = "destroyed"
        terminal["destroyed_at"] = get_timestamp()
        terminal["updated_at"] = terminal["destroyed_at"]
        with remote_state_lock():
            save_terminal_state(terminal)
        result = self._public_terminal(terminal)
        result.update(destroy_result)
        return result

    def _public_terminal(self, terminal: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "terminal_id": terminal["terminal_id"],
            "machine_id": terminal["machine_id"],
            "cwd": terminal["cwd"],
            "backend": terminal.get("backend", "tmux"),
            "status": terminal["status"],
            "created_at": terminal["created_at"],
            "updated_at": terminal.get("updated_at"),
            "destroyed_at": terminal.get("destroyed_at"),
            "last_input": terminal.get("last_input"),
            "transcript_cursor": terminal.get("transcript_cursor", 0),
            "transcript_file_local": terminal["transcript_file_local"],
            "log_dir_local": terminal["log_dir_local"],
            "remote_terminal_name": terminal.get("remote_terminal_name"),
        }


def get_remote_terminal_manager() -> RemoteTerminalManager:
    return RemoteTerminalManager()
