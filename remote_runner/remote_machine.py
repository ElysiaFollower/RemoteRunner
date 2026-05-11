"""Machine registry for the mount-free Remote Runner core."""

from dataclasses import dataclass
import os
from typing import Any, Dict, List, Optional, Sequence

from remote_runner.remote_state import (
    load_machines_state,
    remote_state_lock,
    save_machines_state,
)
from seed_runner.utils import get_timestamp


@dataclass
class RemoteMachine:
    """Remote machine configuration for Remote Runner."""

    machine_id: str
    host: str
    port: int
    user: str
    auth_type: str
    default_cwd: str
    startup_commands: List[str]
    path_mappings: List[Dict[str, str]]
    password: Optional[str] = None
    key_path: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RemoteMachine":
        return cls(
            machine_id=data["machine_id"],
            host=data["host"],
            port=int(data.get("port", 22)),
            user=data["user"],
            auth_type=data["auth_type"],
            default_cwd=data.get("default_cwd") or "~",
            startup_commands=list(data.get("startup_commands") or []),
            path_mappings=list(data.get("path_mappings") or []),
            password=data.get("password"),
            key_path=data.get("key_path"),
        )

    def validate(self) -> None:
        if not self.machine_id:
            raise ValueError("machine_id is required")
        if not self.host:
            raise ValueError("host is required")
        if not self.user:
            raise ValueError("user is required")
        if self.auth_type not in {"key", "password"}:
            raise ValueError("auth_type must be 'key' or 'password'")
        if self.auth_type == "key":
            if not self.key_path:
                raise ValueError("key_path is required for key auth")
            expanded_key_path = os.path.expanduser(self.key_path)
            if not os.path.exists(expanded_key_path):
                raise ValueError(f"key_path not found: {self.key_path}")
        if self.auth_type == "password" and self.password is None:
            raise ValueError("password is required for password auth")
        if not isinstance(self.startup_commands, list):
            raise ValueError("startup_commands must be a list")
        for command in self.startup_commands:
            if not isinstance(command, str) or not command.strip():
                raise ValueError("startup_commands must contain non-empty strings")
        if not isinstance(self.path_mappings, list):
            raise ValueError("path_mappings must be a list")
        for mapping in self.path_mappings:
            if not isinstance(mapping, dict):
                raise ValueError("path_mappings must contain objects")
            command_prefix = mapping.get("command_prefix")
            file_prefix = mapping.get("file_prefix")
            if not isinstance(command_prefix, str) or not command_prefix.strip():
                raise ValueError("path_mappings command_prefix must be a non-empty string")
            if not isinstance(file_prefix, str) or not file_prefix.strip():
                raise ValueError("path_mappings file_prefix must be a non-empty string")

    def to_dict(self, redact: bool = False) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "machine_id": self.machine_id,
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "auth_type": self.auth_type,
            "default_cwd": self.default_cwd,
            "startup_commands": list(self.startup_commands),
            "path_mappings": [dict(mapping) for mapping in self.path_mappings],
        }
        if self.auth_type == "key":
            data["key_path"] = self.key_path
        if self.auth_type == "password":
            data["password"] = "***REDACTED***" if redact else self.password
        return data

    def map_file_path(self, remote_path: str) -> str:
        """Map a command-side path to the path visible to SFTP."""
        for mapping in sorted(
            self.path_mappings,
            key=lambda item: len(item["command_prefix"].rstrip("/")),
            reverse=True,
        ):
            command_prefix = mapping["command_prefix"].rstrip("/") or "/"
            file_prefix = mapping["file_prefix"].rstrip("/") or "/"
            if remote_path == command_prefix:
                return file_prefix
            if remote_path.startswith(f"{command_prefix}/"):
                return f"{file_prefix}{remote_path[len(command_prefix):]}"
        return remote_path


def redact_machine_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Return a public machine record without credential values."""
    machine = RemoteMachine.from_dict(record)
    public = machine.to_dict(redact=True)
    for key in ("created_at", "updated_at"):
        if key in record:
            public[key] = record[key]
    return public


class RemoteMachineManager:
    """Manage Remote Runner machine records."""

    def add(
        self,
        machine_id: str,
        host: str,
        port: int,
        user: str,
        auth_type: str,
        default_cwd: str,
        password: Optional[str] = None,
        key_path: Optional[str] = None,
        startup_commands: Optional[Sequence[str]] = None,
        replace: bool = False,
        confirm_replace: Optional[str] = None,
    ) -> Dict[str, Any]:
        machine = RemoteMachine(
            machine_id=machine_id,
            host=host,
            port=port,
            user=user,
            auth_type=auth_type,
            default_cwd=default_cwd,
            startup_commands=list(startup_commands or []),
            path_mappings=[],
            password=password,
            key_path=key_path,
        )
        machine.validate()

        with remote_state_lock():
            state = load_machines_state()
            machines = state.setdefault("machines", {})
            existing = machines.get(machine_id)
            if existing and not replace:
                raise ValueError(f"Machine '{machine_id}' already exists")
            if existing and confirm_replace != machine_id:
                raise ValueError(f"Replacing Machine '{machine_id}' requires exact confirmation")

            record = machine.to_dict(redact=False)
            now = get_timestamp()
            if existing:
                record["created_at"] = existing.get("created_at", now)
                record["updated_at"] = now
            else:
                record["created_at"] = now
            machines[machine_id] = record
            save_machines_state(state)

        return redact_machine_record(record)

    def configure_path_map(
        self,
        machine_id: str,
        command_prefix: str,
        file_prefix: str,
    ) -> Dict[str, Any]:
        command_prefix = command_prefix.strip()
        file_prefix = file_prefix.strip()
        if not command_prefix:
            raise ValueError("command_prefix is required")
        if not file_prefix:
            raise ValueError("file_prefix is required")
        command_prefix = command_prefix.rstrip("/") or "/"
        file_prefix = file_prefix.rstrip("/") or "/"

        with remote_state_lock():
            state = load_machines_state()
            machines = state.setdefault("machines", {})
            record = machines.get(machine_id)
            if not record:
                raise KeyError(f"Machine '{machine_id}' not found")
            mappings = list(record.get("path_mappings") or [])
            updated = False
            for mapping in mappings:
                if mapping.get("command_prefix", "").rstrip("/") == command_prefix:
                    mapping["command_prefix"] = command_prefix
                    mapping["file_prefix"] = file_prefix
                    updated = True
                    break
            if not updated:
                mappings.append(
                    {
                        "command_prefix": command_prefix,
                        "file_prefix": file_prefix,
                    }
                )
            record["path_mappings"] = mappings
            record["updated_at"] = get_timestamp()
            RemoteMachine.from_dict(record).validate()
            machines[machine_id] = record
            save_machines_state(state)

        return redact_machine_record(record)

    def list(self) -> Dict[str, Any]:
        state = load_machines_state()
        machines = [
            redact_machine_record(record) for _, record in sorted(state.get("machines", {}).items())
        ]
        return {"machines": machines, "summary": {"machine_count": len(machines)}}

    def get(self, machine_id: str) -> RemoteMachine:
        state = load_machines_state()
        record = state.get("machines", {}).get(machine_id)
        if not record:
            raise KeyError(f"Machine '{machine_id}' not found")
        return RemoteMachine.from_dict(record)

    def show(self, machine_id: str) -> Dict[str, Any]:
        state = load_machines_state()
        record = state.get("machines", {}).get(machine_id)
        if not record:
            raise KeyError(f"Machine '{machine_id}' not found")
        return redact_machine_record(record)

    def remove(self, machine_id: str) -> Dict[str, Any]:
        with remote_state_lock():
            state = load_machines_state()
            machines = state.setdefault("machines", {})
            if machine_id not in machines:
                raise KeyError(f"Machine '{machine_id}' not found")
            machines.pop(machine_id)
            save_machines_state(state)
        return {"machine_id": machine_id, "removed": True}

    def configure_startup(
        self,
        machine_id: str,
        startup_commands: Sequence[str],
        default_cwd: Optional[str] = None,
    ) -> Dict[str, Any]:
        raw_commands = list(startup_commands)
        commands = [
            command.strip()
            for command in raw_commands
            if isinstance(command, str) and command.strip()
        ]
        if len(commands) != len(raw_commands):
            raise ValueError("startup_commands must contain non-empty strings")

        with remote_state_lock():
            state = load_machines_state()
            machines = state.setdefault("machines", {})
            record = machines.get(machine_id)
            if not record:
                raise KeyError(f"Machine '{machine_id}' not found")
            record["startup_commands"] = commands
            if default_cwd is not None:
                record["default_cwd"] = default_cwd
            record["updated_at"] = get_timestamp()
            RemoteMachine.from_dict(record).validate()
            machines[machine_id] = record
            save_machines_state(state)

        return redact_machine_record(record)

    def doctor(self, machine_id: str, backend: Any) -> Dict[str, Any]:
        machine = self.get(machine_id)
        return backend.doctor(machine)


def get_remote_machine_manager() -> RemoteMachineManager:
    return RemoteMachineManager()
