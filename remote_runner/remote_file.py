"""Explicit file transfer management for Remote Runner."""

from typing import Any, Dict, Optional

from remote_runner.remote_backend import ParamikoRemoteBackend
from remote_runner.remote_machine import RemoteMachineManager, get_remote_machine_manager
from remote_runner.remote_session import RemoteSessionManager, get_remote_session_manager
from remote_runner.remote_state import (
    append_transfer_record,
    append_artifact_record,
    load_session_state,
    remote_state_lock,
    save_session_state,
)
from remote_runner.utils import generate_id, get_timestamp


class RemoteFileManager:
    """Manage explicit file transfers without requiring mounts."""

    def __init__(
        self,
        machine_manager: Optional[RemoteMachineManager] = None,
        session_manager: Optional[RemoteSessionManager] = None,
        backend: Optional[ParamikoRemoteBackend] = None,
    ):
        self.machine_manager = machine_manager or get_remote_machine_manager()
        self.session_manager = session_manager or get_remote_session_manager()
        self.backend = backend or ParamikoRemoteBackend()

    def put(self, session_id: str, local_path: str, remote_path: str) -> Dict[str, Any]:
        return self._transfer(
            session_id=session_id,
            direction="put",
            source=local_path,
            destination=remote_path,
            action=lambda machine: self.backend.put(machine, local_path, remote_path),
        )

    def get(self, session_id: str, remote_path: str, local_path: str) -> Dict[str, Any]:
        return self._transfer(
            session_id=session_id,
            direction="get",
            source=remote_path,
            destination=local_path,
            action=lambda machine: self.backend.get(machine, remote_path, local_path),
        )

    def list(self, session_id: str, remote_path: str) -> Dict[str, Any]:
        session = load_session_state(session_id)
        if session.get("status") == "destroyed":
            raise RuntimeError(f"Session '{session_id}' has been destroyed")
        machine = self.machine_manager.get(session["machine_id"])
        transfer_id = generate_id("xfer")
        started_at = get_timestamp()
        try:
            result = self.backend.list(machine, remote_path)
            status = "completed"
            error = None
        except Exception as exc:
            result = {"entries": []}
            status = "failed"
            error = str(exc)

        ended_at = get_timestamp()
        record = {
            "transfer_id": transfer_id,
            "session_id": session_id,
            "machine_id": session["machine_id"],
            "direction": "list",
            "source": remote_path,
            "destination": None,
            "started_at": started_at,
            "ended_at": ended_at,
            "status": status,
            "size_bytes": None,
            "sha256": None,
            "error": error,
        }
        self._persist_transfer(session, record)
        if error:
            raise RuntimeError(error)
        response = record.copy()
        response["entries"] = result["entries"]
        return response

    def _transfer(
        self,
        session_id: str,
        direction: str,
        source: str,
        destination: str,
        action: Any,
    ) -> Dict[str, Any]:
        session = load_session_state(session_id)
        if session.get("status") == "destroyed":
            raise RuntimeError(f"Session '{session_id}' has been destroyed")
        machine = self.machine_manager.get(session["machine_id"])
        transfer_id = generate_id("xfer")
        started_at = get_timestamp()
        try:
            result = action(machine)
            status = "completed"
            error = None
        except Exception as exc:
            result = {"size_bytes": None, "sha256": None}
            status = "failed"
            error = str(exc)

        ended_at = get_timestamp()
        record = {
            "transfer_id": transfer_id,
            "session_id": session_id,
            "machine_id": session["machine_id"],
            "direction": direction,
            "source": source,
            "destination": destination,
            "started_at": started_at,
            "ended_at": ended_at,
            "status": status,
            "size_bytes": result.get("size_bytes"),
            "sha256": result.get("sha256"),
            "error": error,
        }
        self._persist_transfer(session, record)
        if error:
            raise RuntimeError(error)
        return record

    def _persist_transfer(self, session: Dict[str, Any], record: Dict[str, Any]) -> None:
        with remote_state_lock():
            current = load_session_state(session["session_id"])
            append_transfer_record(session["session_id"], record)
            if record["direction"] == "get" and record["status"] == "completed":
                append_artifact_record(
                    session["session_id"],
                    {
                        "artifact_id": record["transfer_id"],
                        "transfer_id": record["transfer_id"],
                        "source_remote": record["source"],
                        "local_path": record["destination"],
                        "recorded_at": record["ended_at"],
                        "size_bytes": record["size_bytes"],
                        "sha256": record["sha256"],
                    },
                )
            current["transfer_count"] = int(current.get("transfer_count", 0)) + 1
            session["transfer_count"] = current["transfer_count"]
            save_session_state(current)


def get_remote_file_manager() -> RemoteFileManager:
    return RemoteFileManager()
