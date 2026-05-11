"""SSH/SFTP backend for the mount-free Remote Runner core."""

from dataclasses import dataclass
import hashlib
import os
import posixpath
import re
import shlex
import stat
import time
from typing import Any, Dict, List, Optional
import uuid

import paramiko

from remote_runner.remote_machine import RemoteMachine
from seed_runner.utils import get_timestamp


@dataclass
class RemoteCommandResult:
    stdout: str
    stderr: str
    exit_code: int
    started_at: str
    ended_at: str
    duration_ms: int


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_terminal_output(output: str) -> str:
    output = re.sub(r"\x1b\][^\x07]*(?:\x07|\x1b\\)", "", output)
    output = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", output)
    return output.replace("\r\n", "\n").replace("\r", "\n")


def _find_marker_line(lines: List[str], marker: str) -> Optional[int]:
    for index, line in enumerate(lines):
        if line.strip() == marker:
            return index
    for index, line in enumerate(lines):
        stripped = line.strip()
        if marker in stripped and "printf" not in stripped:
            return index
    return None


def _find_exit_marker_line(lines: List[str], marker: str) -> Optional[int]:
    marker_pattern = re.compile(rf"{re.escape(marker)}:\d+")
    for index, line in enumerate(lines):
        if marker_pattern.fullmatch(line.strip()):
            return index
    for index, line in enumerate(lines):
        stripped = line.strip()
        if marker_pattern.search(stripped) and "printf" not in stripped:
            return index
    return None


def _split_runtime_markers(
    lines: List[str],
    exit_marker: str,
    begin_marker: Optional[str],
) -> List[str]:
    exit_pattern = re.compile(rf"{re.escape(exit_marker)}:\d+")
    expanded: List[str] = []
    for line in lines:
        if begin_marker and begin_marker in line and "printf" not in line:
            prefix, suffix = line.split(begin_marker, 1)
            if prefix:
                expanded.append(prefix)
            expanded.append(begin_marker)
            if suffix:
                expanded.append(suffix)
            continue

        exit_match = exit_pattern.search(line)
        if exit_match and "printf" not in line:
            prefix = line[: exit_match.start()]
            suffix = line[exit_match.end() :]
            if prefix:
                expanded.append(prefix)
            expanded.append(exit_match.group(0))
            if suffix:
                expanded.append(suffix)
            continue

        expanded.append(line)
    return expanded


def _looks_like_echoed_command(line: str, command: str) -> bool:
    stripped = line.strip()
    if stripped == command:
        return True
    return stripped.endswith(command) and any(prompt in stripped for prompt in ("# ", "> ", "$ "))


def _clean_interactive_output(
    output: str,
    exit_marker: str,
    begin_marker: Optional[str] = None,
    command: Optional[str] = None,
) -> str:
    output = _normalize_terminal_output(output)
    lines = _split_runtime_markers(
        output.splitlines(),
        exit_marker=exit_marker,
        begin_marker=begin_marker,
    )
    start_index = -1
    end_index: Optional[int] = None

    if begin_marker:
        found_begin = _find_marker_line(lines, begin_marker)
        if found_begin is not None:
            start_index = found_begin

    found_exit = _find_exit_marker_line(lines, exit_marker)
    if found_exit is not None:
        end_index = found_exit

    if end_index is None:
        selected = lines[start_index + 1 :]
    else:
        selected = lines[start_index + 1 : end_index]

    cleaned_lines = []
    for line in selected:
        if begin_marker and begin_marker in line:
            continue
        if exit_marker in line:
            continue
        if command and _looks_like_echoed_command(line, command):
            continue
        cleaned_lines.append(line)

    output = "\n".join(cleaned_lines)
    output = re.sub(r"\n{3,}", "\n\n", output)
    return output.strip() + "\n" if output.strip() else ""


def _remap_entries_paths(
    entries: List[Dict[str, Any]],
    source_prefix: str,
    display_prefix: str,
) -> List[Dict[str, Any]]:
    source_prefix = source_prefix.rstrip("/") or "/"
    display_prefix = display_prefix.rstrip("/") or "/"
    remapped = []
    for entry in entries:
        item = dict(entry)
        path = item.get("path")
        if isinstance(path, str):
            if path == source_prefix:
                item["path"] = display_prefix
            elif path.startswith(f"{source_prefix}/"):
                item["path"] = f"{display_prefix}{path[len(source_prefix):]}"
        remapped.append(item)
    return remapped


class ParamikoRemoteBackend:
    """Remote backend implemented with SSH and SFTP."""

    def _connect(self, machine: RemoteMachine, timeout: int = 30) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs: Dict[str, Any] = {
            "hostname": machine.host,
            "port": machine.port,
            "username": machine.user,
            "timeout": timeout,
        }
        if machine.auth_type == "key":
            kwargs["key_filename"] = os.path.expanduser(machine.key_path or "")
        else:
            kwargs["password"] = machine.password
        client.connect(**kwargs)
        return client

    def doctor(self, machine: RemoteMachine) -> Dict[str, Any]:
        errors: List[str] = []
        reachable = False
        auth_ok = False
        default_cwd_ok = False
        checked_at = get_timestamp()
        client: Optional[paramiko.SSHClient] = None
        try:
            if machine.startup_commands:
                result = self.run(machine, machine.default_cwd, "pwd", timeout=15)
                reachable = True
                auth_ok = True
                default_cwd_ok = result.exit_code == 0
                if not default_cwd_ok:
                    errors.append(result.stderr or result.stdout)
            else:
                client = self._connect(machine, timeout=15)
                reachable = True
                auth_ok = True
                command = f"cd {shlex.quote(machine.default_cwd)} && pwd"
                _, stdout, stderr = client.exec_command(command, timeout=15)
                exit_code = stdout.channel.recv_exit_status()
                default_cwd_ok = exit_code == 0
                if not default_cwd_ok:
                    errors.append(stderr.read().decode("utf-8", errors="replace").strip())
        except Exception as exc:
            errors.append(str(exc))
        finally:
            if client is not None:
                client.close()

        return {
            "machine_id": machine.machine_id,
            "reachable": reachable,
            "auth_ok": auth_ok,
            "default_cwd_ok": default_cwd_ok,
            "checked_at": checked_at,
            "errors": [error for error in errors if error],
        }

    def run(
        self,
        machine: RemoteMachine,
        cwd: str,
        command: str,
        timeout: int = 300,
    ) -> RemoteCommandResult:
        if machine.startup_commands:
            return self._run_with_startup_commands(machine, cwd, command, timeout=timeout)

        client = self._connect(machine, timeout=timeout)
        started_at = get_timestamp()
        start = time.time()
        try:
            script = f"cd {shlex.quote(cwd)} && {command}"
            remote_cmd = f"bash -lc {shlex.quote(script)}"
            _, stdout_file, stderr_file = client.exec_command(remote_cmd, timeout=timeout)
            stdout = stdout_file.read().decode("utf-8", errors="replace")
            stderr = stderr_file.read().decode("utf-8", errors="replace")
            exit_code = stdout_file.channel.recv_exit_status()
        finally:
            client.close()

        ended_at = get_timestamp()
        return RemoteCommandResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=int((time.time() - start) * 1000),
        )

    def _run_with_startup_commands(
        self,
        machine: RemoteMachine,
        cwd: str,
        command: str,
        timeout: int = 300,
    ) -> RemoteCommandResult:
        client = self._connect(machine, timeout=timeout)
        started_at = get_timestamp()
        start = time.time()
        run_id = uuid.uuid4().hex
        begin_marker = f"__REMOTE_RUNNER_BEGIN_{run_id}__"
        exit_marker = f"__REMOTE_RUNNER_EXIT_{run_id}__"
        output = ""
        exit_code: Optional[int] = None
        try:
            channel = client.invoke_shell(width=200, height=1000)
            lines = list(machine.startup_commands)
            lines.extend(
                [
                    "export PS1='' 2>/dev/null || true",
                    "stty -echo 2>/dev/null || true",
                    f"cd {shlex.quote(cwd)}",
                    f"printf '\\n{begin_marker}\\n'",
                    command,
                    f"printf '\\n{exit_marker}:%s\\n' $?",
                    "stty echo 2>/dev/null || true",
                    "exit",
                    "exit",
                ]
            )
            for line in lines:
                channel.send(line + "\r")

            deadline = time.time() + timeout
            marker_pattern = re.compile(rf"{re.escape(exit_marker)}:(\d+)")
            while time.time() < deadline:
                if channel.recv_ready():
                    output += channel.recv(4096).decode("utf-8", errors="replace")
                    matches = marker_pattern.findall(output)
                    if matches:
                        exit_code = int(matches[-1])
                        break
                elif channel.exit_status_ready():
                    break
                else:
                    time.sleep(0.05)

            if exit_code is None:
                matches = marker_pattern.findall(output)
                if matches:
                    exit_code = int(matches[-1])
                else:
                    raise TimeoutError("Remote startup command execution did not report exit code")
        finally:
            client.close()

        ended_at = get_timestamp()
        cleaned_output = _clean_interactive_output(
            output,
            exit_marker=exit_marker,
            begin_marker=begin_marker,
            command=command,
        )
        return RemoteCommandResult(
            stdout=cleaned_output,
            stderr="",
            exit_code=exit_code,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=int((time.time() - start) * 1000),
        )

    def put(self, machine: RemoteMachine, local_path: str, remote_path: str) -> Dict[str, Any]:
        remote_path = machine.map_file_path(remote_path)
        client = self._connect(machine)
        sftp = client.open_sftp()
        try:
            local_path = os.path.abspath(os.path.expanduser(local_path))
            if os.path.isdir(local_path):
                size = self._put_dir(sftp, local_path, remote_path)
                return {"size_bytes": size, "sha256": None}
            self._mkdir_parent(sftp, remote_path)
            sftp.put(local_path, remote_path)
            return {"size_bytes": os.path.getsize(local_path), "sha256": _sha256_file(local_path)}
        finally:
            sftp.close()
            client.close()

    def get(self, machine: RemoteMachine, remote_path: str, local_path: str) -> Dict[str, Any]:
        remote_path = machine.map_file_path(remote_path)
        client = self._connect(machine)
        sftp = client.open_sftp()
        try:
            local_path = os.path.abspath(os.path.expanduser(local_path))
            remote_stat = sftp.stat(remote_path)
            if stat.S_ISDIR(remote_stat.st_mode):
                size = self._get_dir(sftp, remote_path, local_path)
                return {"size_bytes": size, "sha256": None}
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            sftp.get(remote_path, local_path)
            return {"size_bytes": os.path.getsize(local_path), "sha256": _sha256_file(local_path)}
        finally:
            sftp.close()
            client.close()

    def list(self, machine: RemoteMachine, remote_path: str) -> Dict[str, Any]:
        sftp_path = machine.map_file_path(remote_path)
        client = self._connect(machine)
        sftp = client.open_sftp()
        try:
            entries = []
            for item in sftp.listdir_attr(sftp_path):
                item_type = "directory" if stat.S_ISDIR(item.st_mode) else "file"
                entries.append(
                    {
                        "name": item.filename,
                        "path": posixpath.join(sftp_path, item.filename),
                        "type": item_type,
                        "size_bytes": item.st_size,
                        "mtime": item.st_mtime,
                    }
                )
            return {"entries": _remap_entries_paths(entries, sftp_path, remote_path)}
        finally:
            sftp.close()
            client.close()

    def _mkdir_parent(self, sftp: paramiko.SFTPClient, remote_path: str) -> None:
        parent = posixpath.dirname(remote_path)
        if parent:
            self._mkdir_p(sftp, parent)

    def _mkdir_p(self, sftp: paramiko.SFTPClient, remote_dir: str) -> None:
        if remote_dir in {"", "/"}:
            return
        parts = []
        current = remote_dir
        while current not in {"", "/"}:
            parts.append(current)
            current = posixpath.dirname(current)
        for path in reversed(parts):
            try:
                sftp.stat(path)
            except IOError:
                sftp.mkdir(path)

    def _put_dir(self, sftp: paramiko.SFTPClient, local_dir: str, remote_dir: str) -> int:
        self._mkdir_p(sftp, remote_dir)
        total = 0
        for root, dirs, files in os.walk(local_dir):
            rel = os.path.relpath(root, local_dir)
            remote_root = remote_dir if rel == "." else posixpath.join(remote_dir, rel)
            self._mkdir_p(sftp, remote_root)
            for dirname in dirs:
                self._mkdir_p(sftp, posixpath.join(remote_root, dirname))
            for filename in files:
                local_file = os.path.join(root, filename)
                remote_file = posixpath.join(remote_root, filename)
                sftp.put(local_file, remote_file)
                total += os.path.getsize(local_file)
        return total

    def _get_dir(self, sftp: paramiko.SFTPClient, remote_dir: str, local_dir: str) -> int:
        os.makedirs(local_dir, exist_ok=True)
        total = 0
        for item in sftp.listdir_attr(remote_dir):
            remote_child = posixpath.join(remote_dir, item.filename)
            local_child = os.path.join(local_dir, item.filename)
            if stat.S_ISDIR(item.st_mode):
                total += self._get_dir(sftp, remote_child, local_child)
            else:
                os.makedirs(os.path.dirname(local_child), exist_ok=True)
                sftp.get(remote_child, local_child)
                total += os.path.getsize(local_child)
        return total


def get_remote_backend() -> ParamikoRemoteBackend:
    return ParamikoRemoteBackend()
