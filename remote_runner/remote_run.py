"""Closed-loop run orchestration for Remote Runner."""

from typing import Any, Dict, List, Optional, Sequence

from remote_runner.remote_file import RemoteFileManager, get_remote_file_manager
from remote_runner.remote_session import (
    RemoteSessionManager,
    get_remote_session_manager,
)
from remote_runner.remote_state import (
    list_run_states,
    load_run_state,
    remote_state_lock,
    save_run_state,
)
from seed_runner.utils import generate_id, get_timestamp


class RemoteRunManager:
    """Orchestrate one remote run from existing machine/session/file primitives."""

    def __init__(
        self,
        session_manager: Optional[RemoteSessionManager] = None,
        file_manager: Optional[RemoteFileManager] = None,
    ):
        self.session_manager = session_manager or get_remote_session_manager()
        self.file_manager = file_manager or get_remote_file_manager()

    def once(
        self,
        machine_id: str,
        command: str,
        cwd: Optional[str] = None,
        inputs: Optional[Sequence[Dict[str, str]]] = None,
        artifacts: Optional[Sequence[Dict[str, str]]] = None,
        timeout: int = 300,
        destroy_session: bool = True,
    ) -> Dict[str, Any]:
        run_id = generate_id("run")
        run: Dict[str, Any] = {
            "run_id": run_id,
            "machine_id": machine_id,
            "session_id": None,
            "cwd": cwd,
            "command": command,
            "status": "running",
            "started_at": get_timestamp(),
            "ended_at": None,
            "inputs": [],
            "artifacts": [],
            "command_result": None,
            "destroy_session": destroy_session,
            "destroy_session_result": None,
            "error": None,
        }

        session_id: Optional[str] = None
        try:
            session = self.session_manager.create(machine_id=machine_id, cwd=cwd)
            session_id = session["session_id"]
            run["session_id"] = session_id
            run["cwd"] = session["cwd"]

            input_failed = False
            for item in inputs or []:
                record = self._put_input(session_id, item)
                run["inputs"].append(record)
                if record["status"] != "completed":
                    input_failed = True

            if input_failed:
                run["status"] = "failed"
                run["error"] = "one or more input transfers failed"
            else:
                command_result = self.session_manager.exec(
                    session_id=session_id,
                    command=command,
                    timeout=timeout,
                )
                run["command_result"] = command_result
                run["status"] = "succeeded" if command_result["exit_code"] == 0 else "failed"

                for item in artifacts or []:
                    record = self._get_artifact(session_id, item)
                    run["artifacts"].append(record)
                    if record["status"] != "completed":
                        run["status"] = "failed"
        except Exception as exc:
            run["status"] = "failed"
            run["error"] = str(exc)
        finally:
            if session_id and destroy_session:
                try:
                    run["destroy_session_result"] = self.session_manager.destroy(session_id)
                except Exception as exc:
                    run["status"] = "failed"
                    run["destroy_session_result"] = {
                        "session_id": session_id,
                        "status": "failed",
                        "error": str(exc),
                    }
            run["ended_at"] = get_timestamp()
            with remote_state_lock():
                save_run_state(run)

        return run

    def list(self) -> Dict[str, Any]:
        runs = [
            self._public_run(run)
            for run in sorted(list_run_states(), key=lambda item: item.get("started_at", ""))
        ]
        return {"runs": runs, "summary": {"run_count": len(runs)}}

    def show(self, run_id: str) -> Dict[str, Any]:
        return load_run_state(run_id)

    def _put_input(self, session_id: str, item: Dict[str, str]) -> Dict[str, Any]:
        local_path = item["local_path"]
        remote_path = item["remote_path"]
        try:
            transfer = self.file_manager.put(session_id, local_path, remote_path)
            return {
                "local_path": local_path,
                "remote_path": remote_path,
                "status": transfer["status"],
                "transfer_id": transfer["transfer_id"],
                "size_bytes": transfer.get("size_bytes"),
                "sha256": transfer.get("sha256"),
                "error": transfer.get("error"),
            }
        except Exception as exc:
            return {
                "local_path": local_path,
                "remote_path": remote_path,
                "status": "failed",
                "transfer_id": None,
                "size_bytes": None,
                "sha256": None,
                "error": str(exc),
            }

    def _get_artifact(self, session_id: str, item: Dict[str, str]) -> Dict[str, Any]:
        remote_path = item["remote_path"]
        local_path = item["local_path"]
        try:
            transfer = self.file_manager.get(session_id, remote_path, local_path)
            return {
                "remote_path": remote_path,
                "local_path": local_path,
                "status": transfer["status"],
                "transfer_id": transfer["transfer_id"],
                "size_bytes": transfer.get("size_bytes"),
                "sha256": transfer.get("sha256"),
                "error": transfer.get("error"),
            }
        except Exception as exc:
            return {
                "remote_path": remote_path,
                "local_path": local_path,
                "status": "failed",
                "transfer_id": None,
                "size_bytes": None,
                "sha256": None,
                "error": str(exc),
            }

    def _public_run(self, run: Dict[str, Any]) -> Dict[str, Any]:
        command_result = run.get("command_result") or {}
        return {
            "run_id": run["run_id"],
            "machine_id": run["machine_id"],
            "session_id": run.get("session_id"),
            "cwd": run.get("cwd"),
            "command": run["command"],
            "status": run["status"],
            "started_at": run["started_at"],
            "ended_at": run.get("ended_at"),
            "exit_code": command_result.get("exit_code"),
            "input_count": len(run.get("inputs", [])),
            "artifact_count": len(run.get("artifacts", [])),
        }


def get_remote_run_manager() -> RemoteRunManager:
    return RemoteRunManager()
