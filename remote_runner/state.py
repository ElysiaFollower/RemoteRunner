"""Versioned local state for persistent terminal sessions and instances."""

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from typing import Any, Dict, Iterator, List, Optional

from remote_runner.errors import StateError

STATE_SCHEMA_VERSION = 1
STATE_PRODUCT = "remote-runner-local-terminal"
SESSION_ID_PATTERN = re.compile(r"^sess_[0-9a-f]{32}$")
SAFE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def elapsed_ms(value: Optional[str], *, now: Optional[datetime] = None) -> Optional[int]:
    if value is None:
        return None
    reference = now or datetime.now(timezone.utc)
    return max(0, int((reference - parse_time(value)).total_seconds() * 1000))


class StateStore:
    """Own the on-disk identity and lifecycle records for Remote Runner."""

    def __init__(self, root: Optional[Path] = None) -> None:
        configured = os.environ.get("REMOTE_RUNNER_STATE_DIR")
        selected = root or (
            Path(configured).expanduser() if configured else Path.home() / ".remote-runner"
        )
        self.root = selected.expanduser().resolve()
        self._initialized = False

    @property
    def schema_path(self) -> Path:
        return self.root / "schema.json"

    @property
    def sessions_dir(self) -> Path:
        return self.root / "sessions"

    @property
    def instances_dir(self) -> Path:
        return self.root / "instances"

    @property
    def locks_dir(self) -> Path:
        return self.root / "locks"

    @property
    def diagnostics_dir(self) -> Path:
        return self.root / "diagnostics"

    def initialize(self) -> None:
        if self._initialized:
            return
        initialization_lock = self.root / ".initialize.lock"
        if self.root.exists():
            self._preflight_root(initialization_lock.name)
        else:
            try:
                self.root.mkdir(parents=True, exist_ok=False)
            except FileExistsError:
                self._preflight_root(initialization_lock.name)
        lock_fd = os.open(str(initialization_lock), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            if not self.schema_path.exists():
                existing = self._unversioned_entries(initialization_lock.name)
                if existing:
                    self._raise_incompatible_unversioned_state()
                for temporary in self.root.glob(".schema.json.*"):
                    temporary.unlink()
                self._write_json(
                    self.schema_path,
                    {
                        "product": STATE_PRODUCT,
                        "schema_version": STATE_SCHEMA_VERSION,
                        "created_at": utc_now(),
                    },
                )
            schema = self._read_json(self.schema_path)
            if (
                schema.get("product") != STATE_PRODUCT
                or schema.get("schema_version") != STATE_SCHEMA_VERSION
            ):
                raise StateError(
                    "incompatible_state",
                    (
                        f"State directory '{self.root}' has an incompatible schema; "
                        "Remote Runner does not migrate legacy state"
                    ),
                    context={"state_dir": str(self.root)},
                )
            os.chmod(self.root, 0o700)
            for directory in (
                self.sessions_dir,
                self.instances_dir,
                self.locks_dir,
                self.diagnostics_dir,
            ):
                directory.mkdir(parents=True, exist_ok=True)
                os.chmod(directory, 0o700)
            self._initialized = True
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    def session_dir(self, session_id: str) -> Path:
        self.validate_session_id(session_id)
        return self.sessions_dir / session_id

    def session_state_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "state.json"

    def transcript_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "transcript.log"

    def bootstrap_log_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "bootstrap.log"

    def bootstrap_result_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "bootstrap-result.json"

    def create_session(self, session: Dict[str, Any]) -> None:
        self.initialize()
        session_id = str(session["session_id"])
        directory = self.session_dir(session_id)
        temporary = self.sessions_dir / f".{session_id}.creating-{os.getpid()}-{time.time_ns()}"
        temporary.mkdir(mode=0o700, parents=False, exist_ok=False)
        try:
            transcript = temporary / "transcript.log"
            transcript.touch(mode=0o600, exist_ok=False)
            os.chmod(transcript, 0o600)
            self._write_json(temporary / "state.json", session)
            os.replace(temporary, directory)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    def load_session(self, session_id: str) -> Dict[str, Any]:
        self.initialize()
        path = self.session_state_path(session_id)
        if not path.exists():
            raise StateError(
                "session_not_found",
                f"Session '{session_id}' was not found",
                context={"session_id": session_id},
            )
        return self._read_json(path)

    def save_session(self, session: Dict[str, Any]) -> None:
        self.initialize()
        self._write_json(self.session_state_path(str(session["session_id"])), session)

    def list_sessions(self) -> List[Dict[str, Any]]:
        self.initialize()
        sessions: List[Dict[str, Any]] = []
        for directory in sorted(self.sessions_dir.iterdir()):
            path = directory / "state.json"
            if (
                directory.is_dir()
                and SESSION_ID_PATTERN.fullmatch(directory.name)
                and path.exists()
            ):
                sessions.append(self._read_json(path))
        return sessions

    def purge_session(self, session_id: str) -> None:
        directory = self.session_dir(session_id)
        if directory.exists():
            shutil.rmtree(directory)
        lock_path = self.locks_dir / f"session-{session_id}.lock"
        if lock_path.exists():
            lock_path.unlink()

    def instance_path(self, name: str) -> Path:
        if not SAFE_NAME_PATTERN.fullmatch(name):
            raise StateError(
                "invalid_instance_name",
                "Instance name is not a safe state identifier",
                context={"instance_name": name},
            )
        return self.instances_dir / f"{name}.json"

    def load_instance(self, name: str) -> Dict[str, Any]:
        self.initialize()
        path = self.instance_path(name)
        if not path.exists():
            raise StateError(
                "instance_not_found",
                f"Instance '{name}' was not found",
                context={"instance_name": name},
            )
        return self._read_json(path)

    def save_instance(self, instance: Dict[str, Any]) -> None:
        self.initialize()
        self._write_json(self.instance_path(str(instance["instance_name"])), instance)

    def list_instances(self) -> List[Dict[str, Any]]:
        self.initialize()
        return [self._read_json(path) for path in sorted(self.instances_dir.glob("*.json"))]

    def delete_instance(self, name: str) -> None:
        path = self.instance_path(name)
        if not path.exists():
            raise StateError(
                "instance_not_found",
                f"Instance '{name}' was not found",
                context={"instance_name": name},
            )
        path.unlink()

    @contextmanager
    def state_lock(self) -> Iterator[None]:
        with self._lock(self.locks_dir / "state.lock"):
            yield

    @contextmanager
    def writer_lock(self, session_id: str, timeout: Optional[float] = None) -> Iterator[None]:
        with self._lock(self.locks_dir / f"session-{session_id}.lock", timeout=timeout):
            yield

    @contextmanager
    def _lock(self, path: Path, timeout: Optional[float] = None) -> Iterator[None]:
        self.initialize()
        fd = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o600)
        acquired = False
        deadline = None if timeout is None else time.monotonic() + timeout
        try:
            while True:
                try:
                    flags = fcntl.LOCK_EX if deadline is None else fcntl.LOCK_EX | fcntl.LOCK_NB
                    fcntl.flock(fd, flags)
                    acquired = True
                    break
                except BlockingIOError:
                    if deadline is not None and time.monotonic() >= deadline:
                        raise StateError(
                            "session_write_locked",
                            "Another writer currently owns this Session",
                        )
                    time.sleep(0.05)
            yield
        finally:
            if acquired:
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def write_diagnostic(self, content: str) -> Optional[Path]:
        try:
            self.initialize()
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
            path = self.diagnostics_dir / f"internal-{timestamp}-{os.getpid()}.log"
            path.write_text(content, encoding="utf-8")
            os.chmod(path, 0o600)
            return path
        except Exception:
            return None

    @staticmethod
    def validate_session_id(session_id: str) -> None:
        if not SESSION_ID_PATTERN.fullmatch(session_id):
            raise StateError(
                "invalid_session_id",
                "Session ID must be an exact Remote Runner UUID identifier",
                context={"session_id": session_id},
            )

    def _raise_incompatible_unversioned_state(self) -> None:
        raise StateError(
            "incompatible_state",
            (
                f"State directory '{self.root}' does not use the Local Terminal schema; "
                "archive it and initialize a clean state directory"
            ),
            context={"state_dir": str(self.root)},
        )

    def _preflight_existing_state(self, initialization_lock_name: str) -> None:
        if not self.schema_path.exists():
            if (
                self._unversioned_entries(initialization_lock_name)
                and not (self.root / initialization_lock_name).exists()
            ):
                self._raise_incompatible_unversioned_state()
            return
        schema = self._read_json(self.schema_path)
        if (
            schema.get("product") != STATE_PRODUCT
            or schema.get("schema_version") != STATE_SCHEMA_VERSION
        ):
            raise StateError(
                "incompatible_state",
                (
                    f"State directory '{self.root}' has an incompatible schema; "
                    "Remote Runner does not migrate legacy state"
                ),
                context={"state_dir": str(self.root)},
            )

    def _preflight_root(self, initialization_lock_name: str) -> None:
        if not self.root.is_dir():
            raise StateError(
                "invalid_state_dir",
                f"State path '{self.root}' is not a directory",
                context={"state_dir": str(self.root)},
            )
        self._preflight_existing_state(initialization_lock_name)

    def _unversioned_entries(self, initialization_lock_name: str) -> List[str]:
        return [
            path.name
            for path in self.root.iterdir()
            if path.name not in {"schema.json", initialization_lock_name}
            and not path.name.startswith(".schema.json.")
        ]

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        try:
            with path.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
        except (OSError, json.JSONDecodeError) as error:
            raise StateError(
                "state_unreadable",
                f"Could not read state file '{path}': {error}",
                context={"state_path": str(path)},
            ) from error
        if not isinstance(value, dict):
            raise StateError(
                "state_unreadable",
                f"State file '{path}' must contain a JSON object",
                context={"state_path": str(path)},
            )
        return value

    @staticmethod
    def _write_json(path: Path, value: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
