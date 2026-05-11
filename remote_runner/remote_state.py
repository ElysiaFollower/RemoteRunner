"""Persistent state helpers for the mount-free Remote Runner core."""

from contextlib import contextmanager
import fcntl
import json
import os
from typing import Any, Dict, Iterator, List

from seed_runner.utils import append_file, ensure_dir, read_file, write_file


def get_remote_state_dir() -> str:
    """Return the Remote Runner state directory."""
    configured = os.getenv("REMOTE_RUNNER_STATE_DIR")
    if configured:
        return os.path.abspath(os.path.expanduser(configured))
    return os.path.expanduser("~/.remote-runner")


def get_remote_state_lock_file() -> str:
    return os.path.join(get_remote_state_dir(), "state.lock")


@contextmanager
def remote_state_lock() -> Iterator[None]:
    """Acquire an exclusive lock for Remote Runner state mutations."""
    lock_file = get_remote_state_lock_file()
    ensure_dir(os.path.dirname(lock_file))
    fd = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def ensure_remote_state_dirs() -> None:
    root = get_remote_state_dir()
    ensure_dir(root)
    os.chmod(root, 0o700)
    for name in ("sessions", "logs", "transfers", "artifacts", "runs"):
        path = os.path.join(root, name)
        ensure_dir(path)
        os.chmod(path, 0o700)


def get_machines_file() -> str:
    return os.path.join(get_remote_state_dir(), "machines.json")


def load_machines_state() -> Dict[str, Any]:
    path = get_machines_file()
    if not os.path.exists(path):
        return {"machines": {}}
    data = json.loads(read_file(path))
    data.setdefault("machines", {})
    return data


def save_machines_state(state: Dict[str, Any]) -> None:
    ensure_remote_state_dirs()
    state.setdefault("machines", {})
    path = get_machines_file()
    temp_path = f"{path}.tmp"
    write_file(temp_path, json.dumps(state, indent=2, sort_keys=True))
    os.chmod(temp_path, 0o600)
    os.replace(temp_path, path)


def get_session_file(session_id: str) -> str:
    return os.path.join(get_remote_state_dir(), "sessions", f"{session_id}.json")


def load_session_state(session_id: str) -> Dict[str, Any]:
    path = get_session_file(session_id)
    if not os.path.exists(path):
        raise KeyError(f"Session '{session_id}' not found")
    return json.loads(read_file(path))


def save_session_state(session: Dict[str, Any]) -> None:
    ensure_remote_state_dirs()
    path = get_session_file(session["session_id"])
    temp_path = f"{path}.tmp"
    write_file(temp_path, json.dumps(session, indent=2, sort_keys=True))
    os.chmod(temp_path, 0o600)
    os.replace(temp_path, path)


def list_session_states() -> List[Dict[str, Any]]:
    ensure_remote_state_dirs()
    sessions_dir = os.path.join(get_remote_state_dir(), "sessions")
    sessions: List[Dict[str, Any]] = []
    for filename in sorted(os.listdir(sessions_dir)):
        if not filename.endswith(".json"):
            continue
        sessions.append(json.loads(read_file(os.path.join(sessions_dir, filename))))
    return sessions


def get_log_dir(session_id: str) -> str:
    return os.path.join(get_remote_state_dir(), "logs", session_id)


def get_transfer_file(session_id: str) -> str:
    return os.path.join(get_remote_state_dir(), "transfers", f"{session_id}.jsonl")


def append_transfer_record(session_id: str, record: Dict[str, Any]) -> None:
    ensure_remote_state_dirs()
    path = get_transfer_file(session_id)
    append_file(path, json.dumps(record, sort_keys=True) + "\n")
    os.chmod(path, 0o600)


def load_transfer_records(session_id: str) -> List[Dict[str, Any]]:
    path = get_transfer_file(session_id)
    if not os.path.exists(path):
        return []
    records: List[Dict[str, Any]] = []
    for line in read_file(path).splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def get_artifact_dir(session_id: str) -> str:
    return os.path.join(get_remote_state_dir(), "artifacts", session_id)


def get_artifact_manifest_file(session_id: str) -> str:
    return os.path.join(get_artifact_dir(session_id), "manifest.json")


def load_artifact_manifest(session_id: str) -> Dict[str, Any]:
    path = get_artifact_manifest_file(session_id)
    if not os.path.exists(path):
        return {"session_id": session_id, "artifacts": []}
    manifest = json.loads(read_file(path))
    manifest.setdefault("session_id", session_id)
    manifest.setdefault("artifacts", [])
    return manifest


def append_artifact_record(session_id: str, artifact: Dict[str, Any]) -> None:
    ensure_remote_state_dirs()
    ensure_dir(get_artifact_dir(session_id))
    os.chmod(get_artifact_dir(session_id), 0o700)
    manifest = load_artifact_manifest(session_id)
    manifest.setdefault("artifacts", []).append(artifact)
    path = get_artifact_manifest_file(session_id)
    temp_path = f"{path}.tmp"
    write_file(temp_path, json.dumps(manifest, indent=2, sort_keys=True))
    os.chmod(temp_path, 0o600)
    os.replace(temp_path, path)


def get_run_file(run_id: str) -> str:
    return os.path.join(get_remote_state_dir(), "runs", f"{run_id}.json")


def load_run_state(run_id: str) -> Dict[str, Any]:
    path = get_run_file(run_id)
    if not os.path.exists(path):
        raise KeyError(f"Run '{run_id}' not found")
    return json.loads(read_file(path))


def save_run_state(run: Dict[str, Any]) -> None:
    ensure_remote_state_dirs()
    path = get_run_file(run["run_id"])
    temp_path = f"{path}.tmp"
    write_file(temp_path, json.dumps(run, indent=2, sort_keys=True))
    os.chmod(temp_path, 0o600)
    os.replace(temp_path, path)


def list_run_states() -> List[Dict[str, Any]]:
    ensure_remote_state_dirs()
    runs_dir = os.path.join(get_remote_state_dir(), "runs")
    runs: List[Dict[str, Any]] = []
    for filename in sorted(os.listdir(runs_dir)):
        if not filename.endswith(".json"):
            continue
        runs.append(json.loads(read_file(os.path.join(runs_dir, filename))))
    return runs
