"""Persistent local shell sessions built on one tmux terminal implementation."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
from subprocess import Popen
import sys
import time
from typing import Any, Dict, List, Optional
import uuid

from remote_runner.errors import RemoteRunnerError, StateError, TmuxError
from remote_runner.instance import InstanceManager
from remote_runner.state import StateStore, elapsed_ms, utc_now
from remote_runner.tmux import TmuxTerminal

SESSION_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


@dataclass(frozen=True)
class ReadResult:
    output: bytes
    next_read_cursor: int
    transcript_end_cursor: int


@dataclass(frozen=True)
class TailResult:
    output: bytes
    output_start_cursor: int
    transcript_end_cursor: int


class SessionManager:
    """Own Session identity, lifecycle, bootstrap, state, and transcript ranges."""

    def __init__(
        self,
        *,
        store: Optional[StateStore] = None,
        terminal: Optional[TmuxTerminal] = None,
    ) -> None:
        self.store = store or StateStore()
        self.terminal = terminal or TmuxTerminal()
        self.instances = InstanceManager(self.store)

    def create(
        self,
        *,
        name: Optional[str] = None,
        cwd: Optional[str] = None,
        shell: Optional[str] = None,
        instance_name: Optional[str] = None,
        bootstrap_timeout: float = 60.0,
    ) -> Dict[str, Any]:
        self.terminal.ensure_supported()
        if not math.isfinite(bootstrap_timeout) or bootstrap_timeout <= 0:
            raise RemoteRunnerError(
                "invalid_timeout", "Bootstrap timeout must be a finite number greater than zero"
            )
        session_id = f"sess_{uuid.uuid4().hex}"
        session_name = name or f"shell-{uuid.uuid4().hex[:6]}"
        self._validate_session_name(session_name)
        session_cwd = Path(cwd or os.getcwd()).expanduser().resolve()
        resolved_shell = self.terminal.resolve_shell(shell)
        instance = self.instances.show(instance_name) if instance_name else None
        tmux_safe_name = session_name.replace(".", "_")
        tmux_session_name = f"rr-{tmux_safe_name}-{session_id[5:13]}"
        now = utc_now()
        session: Dict[str, Any] = {
            "schema_version": 1,
            "session_id": session_id,
            "session_name": session_name,
            "session_status": "starting",
            "tmux_session_origin": "created",
            "tmux_session_name": tmux_session_name,
            "tmux_pane_id": None,
            "initial_cwd": str(session_cwd),
            "local_shell_path": resolved_shell,
            "instance_name": instance_name,
            "bootstrap_status": "pending" if instance else "not_requested",
            "bootstrap_started_at": None,
            "bootstrap_ended_at": None,
            "created_at": now,
            "updated_at": now,
            "lost_at": None,
            "destroyed_at": None,
            "last_rr_input_at": None,
        }

        with self.store.state_lock():
            self._assert_name_available(session_name)
            self.store.create_session(session)

        try:
            pane_id = self.terminal.create(
                tmux_session_name=tmux_session_name,
                transcript_path=self.store.transcript_path(session_id),
                cwd=session_cwd,
                shell_path=resolved_shell,
            )
            with self.store.state_lock():
                session = self.store.load_session(session_id)
                session["tmux_pane_id"] = pane_id
                session["session_status"] = "active"
                session["updated_at"] = utc_now()
                self.store.save_session(session)
        except BaseException:
            if self.terminal.session_exists(tmux_session_name):
                self.terminal.destroy(tmux_session_name)
            with self.store.state_lock():
                self.store.purge_session(session_id)
            raise

        if instance is not None:
            self._run_bootstrap(
                session_id=session_id,
                bootstrap_path=str(instance["bootstrap_path"]),
                timeout=bootstrap_timeout,
            )
        return self.show(session_id)

    def register(
        self,
        *,
        tmux_session_name: str,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.terminal.ensure_supported()
        session_id = f"sess_{uuid.uuid4().hex}"
        session_name = name or tmux_session_name
        self._validate_session_name(session_name)
        pane = self.terminal.inspect_existing(tmux_session_name)
        now = utc_now()
        session: Dict[str, Any] = {
            "schema_version": 1,
            "session_id": session_id,
            "session_name": session_name,
            "session_status": "starting",
            "tmux_session_origin": "registered",
            "tmux_session_name": tmux_session_name,
            "tmux_pane_id": pane.pane_id,
            "initial_cwd": pane.current_path,
            "local_shell_path": None,
            "instance_name": None,
            "bootstrap_status": "not_requested",
            "bootstrap_started_at": None,
            "bootstrap_ended_at": None,
            "created_at": now,
            "updated_at": now,
            "lost_at": None,
            "destroyed_at": None,
            "last_rr_input_at": None,
        }

        with self.store.state_lock():
            self._assert_name_available(session_name)
            self._assert_pane_available(pane.pane_id)
            self.store.create_session(session)

        registered = False
        try:
            self.terminal.register_existing(
                tmux_session_name=tmux_session_name,
                expected_pane_id=pane.pane_id,
                session_id=session_id,
                transcript_path=self.store.transcript_path(session_id),
            )
            registered = True
            with self.store.state_lock():
                session = self.store.load_session(session_id)
                session["session_status"] = "active"
                session["updated_at"] = utc_now()
                self.store.save_session(session)
        except BaseException:
            try:
                if registered:
                    self.terminal.unregister_existing(pane.pane_id, session_id)
            finally:
                with self.store.state_lock():
                    self.store.purge_session(session_id)
            raise
        return self.show(session_id)

    def list(self, *, include_destroyed: bool = False) -> Dict[str, Any]:
        sessions: List[Dict[str, Any]] = []
        for record in self.store.list_sessions():
            if not include_destroyed and record.get("session_status") == "destroyed":
                continue
            sessions.append(self.show(str(record["session_id"])))
        return {"sessions": sessions}

    def show(self, session_ref: str) -> Dict[str, Any]:
        session_id = self.resolve_session_id(session_ref)
        session = self._refresh_liveness(session_id)
        return self._public_state(session)

    def send(self, session_ref: str, line: str) -> Dict[str, Any]:
        session_id = self.resolve_session_id(session_ref)
        with self.store.writer_lock(session_id):
            return self._send_locked(session_id, line)

    def key(self, session_ref: str, key: str) -> Dict[str, Any]:
        session_id = self.resolve_session_id(session_ref)
        with self.store.writer_lock(session_id):
            return self._key_locked(session_id, key)

    def read(
        self,
        session_ref: str,
        *,
        from_cursor: int = 0,
        max_bytes: int = 65536,
    ) -> ReadResult:
        session_id = self.resolve_session_id(session_ref)
        self._validate_range(from_cursor, max_bytes)
        path = self.store.transcript_path(session_id)
        try:
            with path.open("rb") as handle:
                transcript_end_cursor = os.fstat(handle.fileno()).st_size
                if from_cursor > transcript_end_cursor:
                    raise RemoteRunnerError(
                        "cursor_out_of_range",
                        (
                            f"Read cursor {from_cursor} is beyond transcript end "
                            f"{transcript_end_cursor}"
                        ),
                        context={"transcript_end_cursor": transcript_end_cursor},
                    )
                handle.seek(from_cursor)
                output = handle.read(min(max_bytes, transcript_end_cursor - from_cursor))
        except OSError as error:
            raise RemoteRunnerError(
                "transcript_read_failed",
                f"Could not read transcript '{path}': {error}",
                context={"transcript_path": str(path)},
            ) from error
        return ReadResult(
            output=output,
            next_read_cursor=from_cursor + len(output),
            transcript_end_cursor=transcript_end_cursor,
        )

    def tail(self, session_ref: str, *, max_bytes: int = 8192) -> TailResult:
        session_id = self.resolve_session_id(session_ref)
        self._validate_range(0, max_bytes)
        path = self.store.transcript_path(session_id)
        try:
            with path.open("rb") as handle:
                transcript_end_cursor = os.fstat(handle.fileno()).st_size
                output_start_cursor = max(0, transcript_end_cursor - max_bytes)
                handle.seek(output_start_cursor)
                output = handle.read(transcript_end_cursor - output_start_cursor)
        except OSError as error:
            raise RemoteRunnerError(
                "transcript_read_failed",
                f"Could not read transcript '{path}': {error}",
                context={"transcript_path": str(path)},
            ) from error
        return TailResult(
            output=output,
            output_start_cursor=output_start_cursor,
            transcript_end_cursor=transcript_end_cursor,
        )

    def attach_argv(self, session_ref: str) -> List[str]:
        session_id = self.resolve_session_id(session_ref)
        session = self._require_live(session_id)
        return self.terminal.attach_argv(str(session["tmux_session_name"]))

    def destroy(self, session_ref: str) -> Dict[str, Any]:
        session_id = self.resolve_session_id(session_ref)
        with self.store.writer_lock(session_id):
            session = self._load_session(session_id)
            if session["session_status"] != "destroyed":
                tmux_name = str(session["tmux_session_name"])
                if self._session_origin(session) == "registered":
                    self.terminal.unregister_existing(str(session["tmux_pane_id"]), session_id)
                elif self.terminal.session_exists(tmux_name):
                    self.terminal.destroy(tmux_name)
                self.terminal.cleanup_startup(self.store.session_dir(session_id))
                now = utc_now()
                session["session_status"] = "destroyed"
                session["destroyed_at"] = now
                session["updated_at"] = now
                self.store.save_session(session)
        return self.show(session_id)

    def purge(self, session_id: str, *, confirm: str) -> Dict[str, Any]:
        self.store.validate_session_id(session_id)
        if session_id != confirm:
            raise RemoteRunnerError(
                "purge_confirmation_required",
                "purge requires the exact Session ID as confirmation",
                context={"session_id": session_id},
            )
        with self.store.state_lock():
            session = self.store.load_session(session_id)
            if session.get("session_status") != "destroyed":
                raise RemoteRunnerError(
                    "session_not_destroyed",
                    "A Session must be destroyed before it can be purged",
                    context={"session_id": session_id},
                )
            self.store.purge_session(session_id)
        return {"session_id": session_id}

    def resolve_session_id(self, session_ref: str) -> str:
        if re.fullmatch(r"sess_[0-9a-f]{32}", session_ref):
            try:
                return str(self.store.load_session(session_ref)["session_id"])
            except StateError as error:
                if error.code != "session_not_found":
                    raise
        matches = [
            session
            for session in self.store.list_sessions()
            if session.get("session_name") == session_ref
            and session.get("session_status") != "destroyed"
        ]
        if not matches:
            raise RemoteRunnerError(
                "session_not_found",
                f"No live Session named '{session_ref}' was found; use Session ID for history",
                context={"session_name": session_ref},
            )
        if len(matches) > 1:
            raise RemoteRunnerError(
                "session_name_ambiguous",
                f"More than one live Session is named '{session_ref}'",
                context={"session_name": session_ref},
            )
        return str(matches[0]["session_id"])

    def _send_locked(self, session_id: str, line: str) -> Dict[str, Any]:
        session = self._require_live(session_id)
        path = self.store.transcript_path(session_id)
        read_from_cursor = path.stat().st_size
        try:
            self.terminal.send_line(str(session["tmux_pane_id"]), line)
        except TmuxError as error:
            if error.code == "multiline_input":
                raise
            self._mark_lost_if_missing(session_id)
            raise RemoteRunnerError(
                "input_outcome_unknown",
                "Terminal input may have been partially sent; inspect the transcript before retrying",
                context={
                    "session_name": session["session_name"],
                    "read_from_cursor": read_from_cursor,
                },
            ) from error
        self._record_rr_input(session_id)
        return {
            "session_name": session["session_name"],
            "read_from_cursor": read_from_cursor,
        }

    def _key_locked(self, session_id: str, key: str) -> Dict[str, Any]:
        session = self._require_live(session_id)
        path = self.store.transcript_path(session_id)
        read_from_cursor = path.stat().st_size
        try:
            self.terminal.send_key(str(session["tmux_pane_id"]), key)
        except TmuxError as error:
            if error.code == "invalid_key":
                raise
            self._mark_lost_if_missing(session_id)
            raise RemoteRunnerError(
                "input_outcome_unknown",
                "Terminal key may have been sent; inspect the transcript before retrying",
                context={
                    "session_name": session["session_name"],
                    "read_from_cursor": read_from_cursor,
                },
            ) from error
        self._record_rr_input(session_id)
        return {
            "session_name": session["session_name"],
            "read_from_cursor": read_from_cursor,
        }

    def _record_rr_input(self, session_id: str) -> None:
        try:
            with self.store.state_lock():
                session = self._load_session(session_id)
                now = utc_now()
                session["last_rr_input_at"] = now
                session["updated_at"] = now
                self.store.save_session(session)
        except Exception as error:
            raise RemoteRunnerError(
                "input_state_update_failed",
                "Input was sent, but state could not be updated; inspect the transcript before retrying",
                context={"session_id": session_id},
            ) from error

    def _require_live(self, session_id: str) -> Dict[str, Any]:
        session = self._refresh_liveness(session_id)
        if session.get("session_status") == "active" and self._session_is_healthy(session):
            return session
        if session.get("session_status") in {"active", "starting"}:
            session = self._mark_lost(session_id)
        raise RemoteRunnerError(
            "session_lost",
            (
                f"Session '{session['session_name']}' no longer has its tmux pane and recorder; "
                "destroy it and create or register a new Session"
            ),
            context={
                "session_name": session["session_name"],
                "session_id": session_id,
            },
        )

    def _refresh_liveness(self, session_id: str) -> Dict[str, Any]:
        session = self._load_session(session_id)
        if session.get("session_status") == "starting":
            if self._session_origin(session) == "registered":
                if self._session_is_healthy(session):
                    with self.store.state_lock():
                        session = self._load_session(session_id)
                        session["session_status"] = "active"
                        session["updated_at"] = utc_now()
                        self.store.save_session(session)
                    return session
                return self._mark_lost(session_id)
            age_ms = elapsed_ms(str(session["updated_at"])) or 0
            deadline = time.monotonic() + max(0.0, (5000 - age_ms) / 1000)
            while True:
                pane_id = session.get("tmux_pane_id")
                if not pane_id:
                    pane_id = self.terminal.pane_id_for_session(str(session["tmux_session_name"]))
                if pane_id and self.terminal.finish_startup(
                    str(pane_id), self.store.session_dir(session_id)
                ):
                    with self.store.state_lock():
                        session = self._load_session(session_id)
                        session["tmux_pane_id"] = pane_id
                        session["session_status"] = "active"
                        session["updated_at"] = utc_now()
                        self.store.save_session(session)
                    return session
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.02)
                session = self._load_session(session_id)
                if session.get("session_status") != "starting":
                    return self._refresh_liveness(session_id)
            return self._mark_lost(session_id)
        if session.get("session_status") == "active" and not self._session_is_healthy(session):
            return self._mark_lost(session_id)
        return session

    def _mark_lost_if_missing(self, session_id: str) -> None:
        session = self._load_session(session_id)
        pane_id = session.get("tmux_pane_id")
        if pane_id and not self._session_is_healthy(session):
            self._mark_lost(session_id)

    def _session_is_healthy(self, session: Dict[str, Any]) -> bool:
        pane_id = str(session["tmux_pane_id"])
        if self._session_origin(session) == "registered":
            return self.terminal.registered_is_healthy(pane_id, str(session["session_id"]))
        return self.terminal.is_healthy(pane_id)

    def _mark_lost(self, session_id: str) -> Dict[str, Any]:
        with self.store.state_lock():
            session = self._load_session(session_id)
            if session.get("session_status") in {"active", "starting"}:
                now = utc_now()
                session["session_status"] = "lost"
                session["lost_at"] = now
                session["updated_at"] = now
                self.store.save_session(session)
        self.terminal.cleanup_startup(self.store.session_dir(session_id))
        return session

    def _public_state(self, session: Dict[str, Any]) -> Dict[str, Any]:
        session_id = str(session["session_id"])
        transcript_path = self.store.transcript_path(session_id)
        try:
            stat = transcript_path.stat()
        except OSError as error:
            raise RemoteRunnerError(
                "transcript_stat_failed",
                f"Could not inspect transcript '{transcript_path}': {error}",
                context={"transcript_path": str(transcript_path)},
            ) from error
        now = datetime.now(timezone.utc)
        last_output_at = None
        if stat.st_size > 0:
            last_output_at = (
                datetime.fromtimestamp(stat.st_mtime, timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )
        state: Dict[str, Any] = {
            "session_id": session_id,
            "session_name": session["session_name"],
            "session_status": session["session_status"],
            "tmux_session_origin": self._session_origin(session),
            "tmux_session_name": session["tmux_session_name"],
            "tmux_pane_id": session["tmux_pane_id"],
            "initial_cwd": session["initial_cwd"],
            "local_shell_path": session["local_shell_path"],
            "instance_name": session.get("instance_name"),
            "bootstrap_status": session.get("bootstrap_status"),
            "created_at": session["created_at"],
            "lost_at": session.get("lost_at"),
            "destroyed_at": session.get("destroyed_at"),
            "last_rr_input_at": session.get("last_rr_input_at"),
            "time_since_last_rr_input_ms": elapsed_ms(session.get("last_rr_input_at"), now=now),
            "last_output_at": last_output_at,
            "time_since_last_output_ms": elapsed_ms(last_output_at, now=now),
            "transcript_path": str(transcript_path),
            "transcript_end_cursor": stat.st_size,
        }
        if session.get("instance_name"):
            state["bootstrap_started_at"] = session.get("bootstrap_started_at")
            state["bootstrap_ended_at"] = session.get("bootstrap_ended_at")
            state["bootstrap_log_path"] = str(self.store.bootstrap_log_path(session_id))
        return state

    def _run_bootstrap(self, *, session_id: str, bootstrap_path: str, timeout: float) -> None:
        result_path = self.store.bootstrap_result_path(session_id)
        result_temporary_path = result_path.with_suffix(".tmp")
        log_path = self.store.bootstrap_log_path(session_id)
        for path in (result_path, result_temporary_path, log_path):
            if path.exists():
                path.unlink()
        with self.store.state_lock():
            session = self._load_session(session_id)
            now = utc_now()
            session["bootstrap_status"] = "running"
            session["bootstrap_started_at"] = now
            session["bootstrap_ended_at"] = None
            session["updated_at"] = now
            self.store.save_session(session)

        command = [
            sys.executable,
            "-m",
            "remote_runner.bootstrap_worker",
            "--state-dir",
            str(self.store.root),
            "--session-id",
            session_id,
            "--bootstrap-path",
            bootstrap_path,
            "--tmux-binary",
            self.terminal.binary,
        ]
        if self.terminal.socket_name:
            command.extend(["--tmux-socket", self.terminal.socket_name])
        try:
            with log_path.open("wb") as log:
                os.chmod(log_path, 0o600)
                process = Popen(
                    command,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                timed_out = False
                try:
                    return_code = process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    try:
                        return_code = process.wait(timeout=1.0)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        return_code = process.wait()
        except OSError as error:
            self._finish_bootstrap(session_id, "failed")
            session = self._load_session(session_id)
            context = {
                "session_name": session["session_name"],
                "session_id": session_id,
            }
            if log_path.exists():
                context["diagnostic_path"] = str(log_path)
            raise RemoteRunnerError(
                "bootstrap_failed",
                f"Bootstrap for Session '{session['session_name']}' could not start: {error}",
                context=context,
            ) from error

        result: Dict[str, Any] = {}
        if result_path.exists():
            try:
                loaded = json.loads(result_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    result = loaded
            except (OSError, json.JSONDecodeError):
                result = {}
            finally:
                result_path.unlink(missing_ok=True)
        result_temporary_path.unlink(missing_ok=True)
        status = "timed_out" if timed_out else "succeeded" if return_code == 0 else "failed"
        session = self._finish_bootstrap(session_id, status)
        if status == "succeeded":
            return
        session_name = str(session["session_name"])
        if status == "timed_out":
            message = f"Bootstrap for Session '{session_name}' exceeded {timeout:g} seconds"
            code = "bootstrap_timed_out"
        else:
            detail = str(result.get("error_message") or "bootstrap hook failed")
            message = f"Bootstrap for Session '{session_name}' failed: {detail}"
            code = "bootstrap_failed"
        raise RemoteRunnerError(
            code,
            message,
            context={
                "session_name": session_name,
                "session_id": session_id,
                "diagnostic_path": str(log_path),
            },
        )

    def _finish_bootstrap(self, session_id: str, status: str) -> Dict[str, Any]:
        with self.store.state_lock():
            session = self._load_session(session_id)
            now = utc_now()
            session["bootstrap_status"] = status
            session["bootstrap_ended_at"] = now
            session["updated_at"] = now
            self.store.save_session(session)
        return session

    def _assert_name_available(self, name: str) -> None:
        for session in self.store.list_sessions():
            if session.get("session_name") == name and session.get("session_status") != "destroyed":
                raise RemoteRunnerError(
                    "session_name_in_use",
                    f"A live Session named '{name}' already exists",
                    context={"session_name": name},
                )

    def _assert_pane_available(self, pane_id: str) -> None:
        for session in self.store.list_sessions():
            if (
                session.get("tmux_pane_id") == pane_id
                and session.get("session_status") != "destroyed"
            ):
                raise RemoteRunnerError(
                    "tmux_pane_already_registered",
                    "The tmux pane already belongs to a live Remote Runner Session",
                    context={
                        "tmux_pane_id": pane_id,
                        "session_id": session["session_id"],
                    },
                )

    @staticmethod
    def _session_origin(session: Dict[str, Any]) -> str:
        return str(session.get("tmux_session_origin", "created"))

    def _load_session(self, session_id: str) -> Dict[str, Any]:
        return self.store.load_session(session_id)

    @staticmethod
    def _validate_session_name(name: str) -> None:
        if not SESSION_NAME_PATTERN.fullmatch(name):
            raise RemoteRunnerError(
                "invalid_session_name",
                (
                    "Session name must start with a letter or number and contain at most 64 "
                    "letters, numbers, '.', '_' or '-'"
                ),
                context={"session_name": name},
            )

    @staticmethod
    def _validate_range(from_cursor: int, max_bytes: int) -> None:
        if from_cursor < 0:
            raise RemoteRunnerError("invalid_cursor", "Cursor must be zero or greater")
        if max_bytes < 0:
            raise RemoteRunnerError("invalid_max_bytes", "max-bytes must be zero or greater")
