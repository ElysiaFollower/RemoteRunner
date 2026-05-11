"""Reusable launch acceptance helpers for Remote Runner tests."""

from __future__ import annotations

import hashlib
import json
import posixpath
import shlex
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List

from remote_runner.remote_backend import RemoteCommandResult
from remote_runner.remote_file import RemoteFileManager
from remote_runner.remote_machine import RemoteMachineManager
from remote_runner.remote_run import RemoteRunManager
from remote_runner.remote_session import RemoteSessionManager
from remote_runner.remote_state import (
    load_artifact_manifest,
    load_machines_state,
    load_run_state,
    load_session_state,
    load_transfer_records,
)


class LaunchBackend:
    """Deterministic fake backend for launch acceptance cases."""

    def __init__(self):
        self.commands: List[Dict[str, Any]] = []
        self.puts: List[Dict[str, str]] = []
        self.gets: List[Dict[str, str]] = []
        self.lists: List[Dict[str, str]] = []
        self.files: Dict[str, str] = {}

    def doctor(self, machine):
        return {
            "machine_id": machine.machine_id,
            "reachable": True,
            "auth_ok": True,
            "default_cwd_ok": True,
            "checked_at": "2026-05-11T00:00:00Z",
            "errors": [],
        }

    def run(self, machine, cwd, command, timeout=300):
        self.commands.append(
            {
                "machine_id": machine.machine_id,
                "cwd": cwd,
                "command": command,
                "timeout": timeout,
            }
        )
        if command == "backend-error":
            raise RuntimeError("ssh failed")
        if command == "exit-seven":
            return RemoteCommandResult(
                stdout="",
                stderr="failed\n",
                exit_code=7,
                started_at="2026-05-11T00:00:01Z",
                ended_at="2026-05-11T00:00:02Z",
                duration_ms=1000,
            )
        if command == "launch-run-once":
            output_path = posixpath.join(cwd, "launch_output.txt")
            self.files[machine.map_file_path(output_path)] = "launch artifact\n"
            stdout = "launch-run-once\n"
        else:
            stdout = f"ran {command}\n"
        return RemoteCommandResult(
            stdout=stdout,
            stderr="",
            exit_code=0,
            started_at="2026-05-11T00:00:01Z",
            ended_at="2026-05-11T00:00:02Z",
            duration_ms=1000,
        )

    def put(self, machine, local_path, remote_path):
        file_path = machine.map_file_path(remote_path)
        self.puts.append(
            {
                "machine_id": machine.machine_id,
                "local_path": local_path,
                "remote_path": remote_path,
                "file_path": file_path,
            }
        )
        content = Path(local_path).read_text()
        self.files[file_path] = content
        return {"size_bytes": len(content.encode()), "sha256": _sha256_text(content)}

    def get(self, machine, remote_path, local_path):
        file_path = machine.map_file_path(remote_path)
        self.gets.append(
            {
                "machine_id": machine.machine_id,
                "remote_path": remote_path,
                "file_path": file_path,
                "local_path": local_path,
            }
        )
        if file_path not in self.files:
            raise FileNotFoundError(remote_path)
        content = self.files[file_path]
        Path(local_path).write_text(content)
        return {"size_bytes": len(content.encode()), "sha256": _sha256_text(content)}

    def list(self, machine, remote_path):
        file_path = machine.map_file_path(remote_path)
        self.lists.append(
            {
                "machine_id": machine.machine_id,
                "remote_path": remote_path,
                "file_path": file_path,
            }
        )
        prefix = file_path.rstrip("/")
        display_prefix = remote_path.rstrip("/")
        entries = []
        for path, content in sorted(self.files.items()):
            if path == prefix or path.startswith(prefix + "/"):
                display_path = (
                    display_prefix if path == prefix else f"{display_prefix}{path[len(prefix):]}"
                )
                entries.append(
                    {
                        "name": Path(path).name,
                        "path": display_path,
                        "type": "file",
                        "size_bytes": len(content.encode()),
                        "mtime": 1778198400,
                    }
                )
        return {"entries": entries}


def _sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _run_remote_runner(*args: str) -> Dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-m", "remote_runner.cli", *args],
        capture_output=True,
        text=True,
        timeout=60,
    )
    output = result.stdout.strip() or result.stderr.strip()
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"remote-runner returned non-JSON output\n"
            f"args={args!r}\nstdout={result.stdout}\nstderr={result.stderr}"
        ) from exc
    if result.returncode != 0:
        raise AssertionError(f"remote-runner failed: {payload}")
    return payload


def assert_launch_public_contract() -> None:
    from remote_runner.cli import main as target_main
    from seed_runner.remote_cli import main as legacy_main
    from seed_runner import utils as legacy_utils
    from remote_runner import utils as target_utils

    assert target_main.__module__ == "remote_runner.cli"
    assert legacy_main is target_main
    assert legacy_utils.get_timestamp is target_utils.get_timestamp
    assert legacy_utils.generate_id is target_utils.generate_id


def run_fake_launch_smoke(tmp_path: Path) -> Dict[str, Any]:
    machine_manager = RemoteMachineManager()
    machine_manager.add(
        machine_id="launch-lab-01",
        host="launch.example.internal",
        port=22,
        user="deploy",
        auth_type="password",
        password="launch-secret",
        default_cwd="/srv/app",
        startup_commands=["wsl"],
    )
    machine_manager.configure_path_map("launch-lab-01", "/srv/app", "C:/srv/app")
    backend = LaunchBackend()
    doctor = machine_manager.doctor("launch-lab-01", backend)
    session_manager = RemoteSessionManager(machine_manager=machine_manager, backend=backend)
    file_manager = RemoteFileManager(
        machine_manager=machine_manager,
        session_manager=session_manager,
        backend=backend,
    )
    run_manager = RemoteRunManager(
        session_manager=session_manager,
        file_manager=file_manager,
    )

    session = session_manager.create("launch-lab-01")
    session_id = session["session_id"]
    exec_result = session_manager.exec(session_id, "echo launch-ready")

    local_input = tmp_path / "launch_input.txt"
    local_input.write_text("launch input\n")
    local_download = tmp_path / "launch_download.txt"
    remote_input = "/srv/app/launch_input.txt"
    put = file_manager.put(session_id, str(local_input), remote_input)
    listing = file_manager.list(session_id, "/srv/app")
    get = file_manager.get(session_id, remote_input, str(local_download))

    local_run_input = tmp_path / "launch_run_input.txt"
    local_run_input.write_text("launch run input\n")
    local_run_output = tmp_path / "launch_run_output.txt"
    remote_run_input = "/srv/app/launch_run_input.txt"
    remote_run_output = "/srv/app/launch_output.txt"
    run = run_manager.once(
        machine_id="launch-lab-01",
        cwd="/srv/app",
        command="launch-run-once",
        inputs=[
            {
                "local_path": str(local_run_input),
                "remote_path": remote_run_input,
            }
        ],
        artifacts=[
            {
                "remote_path": remote_run_output,
                "local_path": str(local_run_output),
            }
        ],
    )

    logs = session_manager.logs(session_id)
    destroyed = session_manager.destroy(session_id)

    return {
        "doctor": doctor,
        "session": session,
        "exec": exec_result,
        "put": put,
        "list": listing,
        "get": get,
        "download": local_download.read_text(),
        "run": run,
        "run_input": local_run_input.read_text(),
        "run_output": local_run_output.read_text(),
        "logs": logs,
        "destroyed": destroyed,
        "machine_state": machine_manager.show("launch-lab-01"),
        "machine_list": machine_manager.list(),
        "machine_state_record": load_machines_state(),
        "backend_puts": backend.puts,
        "backend_gets": backend.gets,
        "backend_lists": backend.lists,
        "transfer_records": load_transfer_records(session_id),
        "session_state": load_session_state(session_id),
        "run_state": load_run_state(run["run_id"]),
        "artifact_manifest": load_artifact_manifest(run["session_id"]),
    }


def run_real_launch_smoke(machine_id: str, remote_cwd: str, tmp_path: Path) -> Dict[str, Any]:
    remote_cwd = remote_cwd.rstrip("/")
    probe_id = uuid.uuid4().hex
    probe_name = f"rr_launch_smoke_{probe_id}.txt"
    remote_probe_path = posixpath.join(remote_cwd, probe_name)
    local_source = tmp_path / probe_name
    local_download = tmp_path / f"downloaded_{probe_name}"
    content = f"remote-runner-launch-smoke {probe_id}\n"
    local_source.write_text(content)

    run_input_name = f"rr_launch_input_{probe_id}.txt"
    run_input_path = posixpath.join(remote_cwd, run_input_name)
    local_run_input = tmp_path / run_input_name
    local_run_input.write_text(content)

    run_output_name = f"rr_launch_output_{probe_id}.txt"
    run_output_path = posixpath.join(remote_cwd, run_output_name)
    local_run_output = tmp_path / f"downloaded_{run_output_name}"

    session_id = None
    cleanup_done = False
    try:
        doctor = _run_remote_runner("machine", "doctor", machine_id, "--json")
        session = _run_remote_runner(
            "session",
            "create",
            "--machine",
            machine_id,
            "--cwd",
            remote_cwd,
            "--json",
        )
        session_id = session["session_id"]

        exec_result = _run_remote_runner(
            "session",
            "exec",
            "--session",
            session_id,
            "--cmd",
            'pwd && printf "launch-ready\\n"',
            "--json",
        )

        put = _run_remote_runner(
            "file",
            "put",
            "--session",
            session_id,
            "--local",
            str(local_source),
            "--remote",
            remote_probe_path,
            "--json",
        )

        listing = _run_remote_runner(
            "file",
            "list",
            "--session",
            session_id,
            "--remote",
            remote_cwd,
            "--json",
        )

        get = _run_remote_runner(
            "file",
            "get",
            "--session",
            session_id,
            "--remote",
            remote_probe_path,
            "--local",
            str(local_download),
            "--json",
        )

        run = _run_remote_runner(
            "run",
            "once",
            "--machine",
            machine_id,
            "--cwd",
            remote_cwd,
            "--input",
            f"{local_run_input}={run_input_path}",
            "--artifact",
            f"{run_output_path}={local_run_output}",
            "--cmd",
            f"cp {shlex.quote(run_input_name)} {shlex.quote(run_output_name)}",
            "--json",
        )

        cleanup = _run_remote_runner(
            "session",
            "exec",
            "--session",
            session_id,
            "--cmd",
            (
                f"rm -f {shlex.quote(probe_name)} {shlex.quote(run_input_name)} "
                f"{shlex.quote(run_output_name)} && "
                f"test ! -e {shlex.quote(probe_name)} && "
                f"test ! -e {shlex.quote(run_input_name)} && "
                f"test ! -e {shlex.quote(run_output_name)}"
            ),
            "--json",
        )
        cleanup_done = cleanup["exit_code"] == 0

        return {
            "doctor": doctor,
            "session": session,
            "exec": exec_result,
            "probe_name": probe_name,
            "put": put,
            "listing": listing,
            "get": get,
            "run": run,
            "cleanup": cleanup,
            "download": local_download.read_text(),
            "run_input": local_run_input.read_text(),
            "run_output": local_run_output.read_text(),
        }
    finally:
        if session_id and not cleanup_done:
            _run_remote_runner(
                "session",
                "exec",
                "--session",
                session_id,
                "--cmd",
                (
                    f"rm -f {shlex.quote(probe_name)} {shlex.quote(run_input_name)} "
                    f"{shlex.quote(run_output_name)}"
                ),
                "--json",
            )
        if session_id:
            _run_remote_runner("session", "destroy", "--session", session_id, "--json")
