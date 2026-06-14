"""SSH/SFTP backend for the mount-free Remote Runner core."""

import base64
import codecs
from dataclasses import dataclass
import hashlib
import json
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
from remote_runner.utils import get_timestamp
from remote_runner.windows_agent import WINDOWS_AGENT_SOURCE


@dataclass
class RemoteCommandResult:
    stdout: str
    stderr: str
    exit_code: int
    started_at: str
    ended_at: str
    duration_ms: int


DEFAULT_BACKGROUND_OUTPUT_LIMIT = 8192


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

    def _uses_windows_agent(self, machine: RemoteMachine) -> bool:
        return machine.backend == "windows-agent"

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
        if self._uses_windows_agent(machine):
            return self._doctor_windows_agent(machine)

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
            decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            while time.time() < deadline:
                if channel.recv_ready():
                    output += decoder.decode(channel.recv(4096))
                    search_window = output[-(len(exit_marker) + 100) :]
                    matches = marker_pattern.findall(search_window)
                    if matches:
                        exit_code = int(matches[-1])
                        break
                elif channel.exit_status_ready():
                    break
                else:
                    time.sleep(0.05)

            output += decoder.decode(b"", final=True)
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

    def start_background(
        self,
        machine: RemoteMachine,
        cwd: str,
        command: str,
        command_id: str,
        timeout: int = 15,
    ) -> Dict[str, Any]:
        if machine.startup_commands:
            raise RuntimeError("background commands do not yet support startup_commands machines")

        remote_state_dir = posixpath.join(cwd, ".remote-runner", "commands", command_id)
        remote_stdout_file = posixpath.join(remote_state_dir, "stdout.log")
        remote_stderr_file = posixpath.join(remote_state_dir, "stderr.log")
        remote_status_file = posixpath.join(remote_state_dir, "status")
        remote_pid_file = posixpath.join(remote_state_dir, "pid")
        remote_exit_code_file = posixpath.join(remote_state_dir, "exit_code")
        remote_ended_at_file = posixpath.join(remote_state_dir, "ended_at")
        remote_worker_file = posixpath.join(remote_state_dir, "worker.sh")
        remote_launcher_file = posixpath.join(remote_state_dir, "launch.sh")

        sftp_state_dir = machine.map_file_path(remote_state_dir)
        sftp_worker_file = machine.map_file_path(remote_worker_file)
        sftp_launcher_file = machine.map_file_path(remote_launcher_file)

        worker_script = self._background_worker_script(
            remote_state_dir=remote_state_dir,
            cwd=cwd,
            command=command,
        )
        launcher_script = self._background_launcher_script(
            remote_state_dir=remote_state_dir,
            remote_worker_file=remote_worker_file,
            remote_stdout_file=remote_stdout_file,
            remote_stderr_file=remote_stderr_file,
            remote_status_file=remote_status_file,
            remote_pid_file=remote_pid_file,
        )

        client = self._connect(machine, timeout=timeout)
        sftp = client.open_sftp()
        try:
            self._mkdir_p(sftp, sftp_state_dir)
            self._write_remote_script(sftp, sftp_worker_file, worker_script)
            self._write_remote_script(sftp, sftp_launcher_file, launcher_script)
            remote_cmd = f"bash {shlex.quote(remote_launcher_file)}"
            _, stdout_file, stderr_file = client.exec_command(remote_cmd, timeout=timeout)
            stdout = stdout_file.read().decode("utf-8", errors="replace")
            stderr = stderr_file.read().decode("utf-8", errors="replace")
            exit_code = stdout_file.channel.recv_exit_status()
            if exit_code != 0:
                raise RuntimeError(stderr.strip() or stdout.strip() or "background launch failed")
            pid = self._parse_background_launch_pid(stdout)
            return {
                "remote_state_dir": remote_state_dir,
                "remote_stdout_file": remote_stdout_file,
                "remote_stderr_file": remote_stderr_file,
                "remote_status_file": remote_status_file,
                "remote_pid_file": remote_pid_file,
                "remote_exit_code_file": remote_exit_code_file,
                "remote_ended_at_file": remote_ended_at_file,
                "remote_worker_file": remote_worker_file,
                "remote_pid": pid,
            }
        finally:
            sftp.close()
            client.close()

    def inspect_background(
        self,
        machine: RemoteMachine,
        command_record: Dict[str, Any],
        stdout_limit: int = DEFAULT_BACKGROUND_OUTPUT_LIMIT,
        stderr_limit: int = DEFAULT_BACKGROUND_OUTPUT_LIMIT,
    ) -> Dict[str, Any]:
        if machine.startup_commands:
            raise RuntimeError("background commands do not yet support startup_commands machines")

        client = self._connect(machine)
        sftp = client.open_sftp()
        try:
            status = self._read_remote_text(sftp, machine, command_record["remote_status_file"])
            status = status.strip() or "running"
            exit_code_text = self._read_remote_text(
                sftp,
                machine,
                command_record["remote_exit_code_file"],
                missing_ok=True,
            ).strip()
            ended_at = self._read_remote_text(
                sftp,
                machine,
                command_record["remote_ended_at_file"],
                missing_ok=True,
            ).strip()
            stdout, stdout_truncated = self._read_remote_text_limited(
                sftp,
                machine,
                command_record["remote_stdout_file"],
                stdout_limit,
            )
            stderr, stderr_truncated = self._read_remote_text_limited(
                sftp,
                machine,
                command_record["remote_stderr_file"],
                stderr_limit,
            )
            exit_code = int(exit_code_text) if exit_code_text else None

            if status == "running" and exit_code is None:
                alive = self._remote_pid_alive(client, command_record.get("remote_pid"))
                if not alive:
                    status = "failed"

            if exit_code is not None and status == "running":
                status = "exited"

            return {
                "status": status,
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
                "ended_at": ended_at or None,
            }
        finally:
            sftp.close()
            client.close()

    def stop_background(
        self,
        machine: RemoteMachine,
        command_record: Dict[str, Any],
    ) -> Dict[str, Any]:
        if machine.startup_commands:
            raise RuntimeError("background commands do not yet support startup_commands machines")

        pid = command_record.get("remote_pid")
        if not pid:
            raise RuntimeError("background command has no remote pid")

        status_file = command_record["remote_status_file"]
        exit_code_file = command_record["remote_exit_code_file"]
        ended_at_file = command_record["remote_ended_at_file"]
        script = (
            f"pid={shlex.quote(str(pid))}; "
            "if kill -0 \"$pid\" 2>/dev/null; then "
            "kill -TERM -- \"-$pid\" 2>/dev/null || kill -TERM \"$pid\" 2>/dev/null || true; "
            "sleep 0.3; "
            "if kill -0 \"$pid\" 2>/dev/null; then "
            "kill -KILL -- \"-$pid\" 2>/dev/null || kill -KILL \"$pid\" 2>/dev/null || true; "
            "fi; "
            f"printf '%s\\n' stopped > {shlex.quote(status_file)}; "
            f"printf '%s\\n' 143 > {shlex.quote(exit_code_file)}; "
            f"date -u +'%Y-%m-%dT%H:%M:%SZ' > {shlex.quote(ended_at_file)}; "
            "printf '%s\\n' stopped; "
            "else "
            "printf '%s\\n' not_running; "
            "fi"
        )
        client = self._connect(machine)
        try:
            _, stdout_file, stderr_file = client.exec_command(f"bash -lc {shlex.quote(script)}")
            stdout = stdout_file.read().decode("utf-8", errors="replace").strip()
            stderr = stderr_file.read().decode("utf-8", errors="replace").strip()
            exit_code = stdout_file.channel.recv_exit_status()
            if exit_code != 0:
                raise RuntimeError(stderr or stdout or "background stop failed")
            return {"stop_result": stdout or "unknown"}
        finally:
            client.close()

    def create_terminal(
        self,
        machine: RemoteMachine,
        cwd: str,
        terminal_id: str,
        width: int = 120,
        height: int = 40,
        history_limit: int = 10000,
    ) -> Dict[str, Any]:
        if self._uses_windows_agent(machine):
            return self._create_windows_agent_terminal(
                machine=machine,
                cwd=cwd,
                terminal_id=terminal_id,
            )

        if machine.startup_commands:
            raise RuntimeError("terminal sessions do not yet support startup_commands machines")

        tmux_session = self._tmux_session_name(terminal_id)
        script = " && ".join(
            [
                "command -v tmux >/dev/null 2>&1",
                "command -v bash >/dev/null 2>&1",
                (
                    f"tmux new-session -d -s {shlex.quote(tmux_session)} "
                    f"-c {shlex.quote(cwd)} bash --noprofile --norc"
                ),
                (
                    f"tmux resize-window -t {shlex.quote(tmux_session)} "
                    f"-x {int(width)} -y {int(height)}"
                ),
                (
                    f"tmux set-option -t {shlex.quote(tmux_session)} "
                    f"history-limit {int(history_limit)}"
                ),
                f"printf '%s\\n' {shlex.quote(tmux_session)}",
            ]
        )
        client = self._connect(machine)
        try:
            _, stdout_file, stderr_file = client.exec_command(f"bash -lc {shlex.quote(script)}")
            stdout = stdout_file.read().decode("utf-8", errors="replace").strip()
            stderr = stderr_file.read().decode("utf-8", errors="replace").strip()
            exit_code = stdout_file.channel.recv_exit_status()
            if exit_code != 0:
                raise RuntimeError(stderr or stdout or "terminal create failed")
            return {
                "backend": "tmux",
                "remote_terminal_name": stdout or tmux_session,
                "history_limit": history_limit,
                "width": width,
                "height": height,
            }
        finally:
            client.close()

    def start_session_command(
        self,
        machine: RemoteMachine,
        session_record: Dict[str, Any],
        command: str,
        command_id: str,
        cwd: Optional[str] = None,
        cwd_override: bool = False,
    ) -> Dict[str, Any]:
        if self._uses_windows_agent(machine):
            return self._start_windows_agent_session_command(
                machine=machine,
                session_record=session_record,
                command=command,
                command_id=command_id,
                cwd=cwd if cwd_override else None,
            )

        if machine.startup_commands:
            raise RuntimeError("persistent session commands do not yet support startup_commands machines")

        paths = self._session_command_paths(session_record["cwd"], command_id)
        sftp_paths = {key: machine.map_file_path(value) for key, value in paths.items()}
        wrapper_script = self._session_command_wrapper_script(
            paths=paths,
            command=command,
            command_id=command_id,
            cwd=cwd,
            cwd_override=cwd_override,
        )

        client = self._connect(machine)
        sftp = client.open_sftp()
        try:
            self._mkdir_p(sftp, sftp_paths["remote_state_dir"])
            self._write_remote_script(sftp, sftp_paths["remote_wrapper_file"], wrapper_script)
        finally:
            sftp.close()
            client.close()

        self.send_terminal_input(
            machine=machine,
            terminal_record=session_record,
            input_text=f"source {shlex.quote(paths['remote_wrapper_file'])}",
            enter=True,
        )
        return {
            "command_backend": "tmux",
            **paths,
        }

    def wait_session_command(
        self,
        machine: RemoteMachine,
        command_record: Dict[str, Any],
        timeout: int = 300,
        stdout_limit: int = DEFAULT_BACKGROUND_OUTPUT_LIMIT,
        stderr_limit: int = DEFAULT_BACKGROUND_OUTPUT_LIMIT,
    ) -> Dict[str, Any]:
        if self._uses_windows_agent(machine):
            deadline = time.time() + max(0, timeout)
            while True:
                result = self.inspect_session_command(
                    machine=machine,
                    command_record=command_record,
                    stdout_limit=stdout_limit,
                    stderr_limit=stderr_limit,
                )
                if result["status"] != "running":
                    return result
                if time.time() >= deadline:
                    raise TimeoutError("Windows agent command did not finish before timeout")
                time.sleep(min(0.2, max(0, deadline - time.time())))

        deadline = time.time() + max(0, timeout)
        while True:
            result = self.inspect_session_command(
                machine=machine,
                command_record=command_record,
                stdout_limit=stdout_limit,
                stderr_limit=stderr_limit,
            )
            if result["status"] != "running":
                return result
            if time.time() >= deadline:
                raise TimeoutError("persistent session command did not finish before timeout")
            time.sleep(min(0.2, max(0, deadline - time.time())))

    def inspect_session_command(
        self,
        machine: RemoteMachine,
        command_record: Dict[str, Any],
        stdout_limit: int = DEFAULT_BACKGROUND_OUTPUT_LIMIT,
        stderr_limit: int = DEFAULT_BACKGROUND_OUTPUT_LIMIT,
    ) -> Dict[str, Any]:
        if self._uses_windows_agent(machine):
            return self._inspect_windows_agent_session_command(
                machine=machine,
                command_record=command_record,
                stdout_limit=stdout_limit,
                stderr_limit=stderr_limit,
            )

        if machine.startup_commands:
            raise RuntimeError("persistent session commands do not yet support startup_commands machines")

        client = self._connect(machine)
        sftp = client.open_sftp()
        try:
            status = self._read_remote_text(
                sftp,
                machine,
                command_record["remote_status_file"],
                missing_ok=True,
            ).strip()
            status = status or "running"
            exit_code_text = self._read_remote_text(
                sftp,
                machine,
                command_record["remote_exit_code_file"],
                missing_ok=True,
            ).strip()
            started_at = self._read_remote_text(
                sftp,
                machine,
                command_record["remote_started_at_file"],
                missing_ok=True,
            ).strip()
            ended_at = self._read_remote_text(
                sftp,
                machine,
                command_record["remote_ended_at_file"],
                missing_ok=True,
            ).strip()
            stdout, stdout_truncated = self._read_remote_text_limited(
                sftp,
                machine,
                command_record["remote_stdout_file"],
                stdout_limit,
            )
            stderr, stderr_truncated = self._read_remote_text_limited(
                sftp,
                machine,
                command_record["remote_stderr_file"],
                stderr_limit,
            )
            exit_code = int(exit_code_text) if exit_code_text else None
            return {
                "status": status,
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
                "started_at": started_at or None,
                "ended_at": ended_at or None,
            }
        finally:
            sftp.close()
            client.close()

    def stop_session_command(
        self,
        machine: RemoteMachine,
        session_record: Dict[str, Any],
        command_record: Dict[str, Any],
    ) -> Dict[str, Any]:
        if self._uses_windows_agent(machine):
            raise RuntimeError("Windows agent session command stop is not yet supported")

        if machine.startup_commands:
            raise RuntimeError("persistent session commands do not yet support startup_commands machines")

        target = session_record["remote_terminal_name"]
        client = self._connect(machine)
        try:
            stop_script = (
                f"tmux send-keys -t {shlex.quote(target)} C-c; "
                "sleep 0.2; "
                f"printf '%s\\n' stopped > {shlex.quote(command_record['remote_status_file'])}; "
                f"printf '%s\\n' 143 > {shlex.quote(command_record['remote_exit_code_file'])}; "
                f"date -u +'%Y-%m-%dT%H:%M:%SZ' > {shlex.quote(command_record['remote_ended_at_file'])}"
            )
            _, stdout_file, stderr_file = client.exec_command(f"bash -lc {shlex.quote(stop_script)}")
            stdout = stdout_file.read().decode("utf-8", errors="replace").strip()
            stderr = stderr_file.read().decode("utf-8", errors="replace").strip()
            exit_code = stdout_file.channel.recv_exit_status()
            if exit_code != 0:
                raise RuntimeError(stderr or stdout or "session command stop failed")
        finally:
            client.close()

        deadline = time.time() + 5
        latest: Dict[str, Any] = {"status": "running"}
        while time.time() < deadline:
            latest = self.inspect_session_command(machine, command_record)
            if latest["status"] != "running":
                break
            time.sleep(0.2)
        return {"stop_result": latest.get("status", "unknown")}

    def send_terminal_input(
        self,
        machine: RemoteMachine,
        terminal_record: Dict[str, Any],
        input_text: str,
        enter: bool = True,
    ) -> Dict[str, Any]:
        if self._uses_windows_agent(machine):
            return self._send_windows_agent_input(
                machine=machine,
                terminal_record=terminal_record,
                input_text=input_text,
                enter=enter,
            )

        if machine.startup_commands:
            raise RuntimeError("terminal sessions do not yet support startup_commands machines")

        target = terminal_record["remote_terminal_name"]
        commands = [
            (
                f"tmux send-keys -t {shlex.quote(target)} "
                f"-l -- {shlex.quote(input_text)}"
            )
        ]
        if enter:
            commands.append(f"tmux send-keys -t {shlex.quote(target)} C-m")
        script = " && ".join(commands)
        client = self._connect(machine)
        try:
            _, stdout_file, stderr_file = client.exec_command(f"bash -lc {shlex.quote(script)}")
            stdout = stdout_file.read().decode("utf-8", errors="replace").strip()
            stderr = stderr_file.read().decode("utf-8", errors="replace").strip()
            exit_code = stdout_file.channel.recv_exit_status()
            if exit_code != 0:
                raise RuntimeError(stderr or stdout or "terminal send failed")
            return {"input_sent": True}
        finally:
            client.close()

    def capture_terminal(
        self,
        machine: RemoteMachine,
        terminal_record: Dict[str, Any],
    ) -> Dict[str, Any]:
        if self._uses_windows_agent(machine):
            return self._capture_windows_agent_terminal(machine, terminal_record)

        if machine.startup_commands:
            raise RuntimeError("terminal sessions do not yet support startup_commands machines")

        target = terminal_record["remote_terminal_name"]
        history_limit = int(terminal_record.get("history_limit") or 10000)
        script = (
            f"tmux has-session -t {shlex.quote(target)} >/dev/null 2>&1 && "
            f"tmux capture-pane -t {shlex.quote(target)} -p -S -{history_limit}"
        )
        client = self._connect(machine)
        try:
            _, stdout_file, stderr_file = client.exec_command(f"bash -lc {shlex.quote(script)}")
            stdout = stdout_file.read().decode("utf-8", errors="replace")
            stderr = stderr_file.read().decode("utf-8", errors="replace").strip()
            exit_code = stdout_file.channel.recv_exit_status()
            if exit_code != 0:
                raise RuntimeError(stderr or "terminal capture failed")
            return {"status": "active", "transcript": stdout}
        finally:
            client.close()

    def destroy_terminal(
        self,
        machine: RemoteMachine,
        terminal_record: Dict[str, Any],
    ) -> Dict[str, Any]:
        if self._uses_windows_agent(machine):
            return self._destroy_windows_agent_terminal(machine, terminal_record)

        if machine.startup_commands:
            raise RuntimeError("terminal sessions do not yet support startup_commands machines")

        target = terminal_record["remote_terminal_name"]
        script = (
            f"if tmux has-session -t {shlex.quote(target)} >/dev/null 2>&1; then "
            f"tmux kill-session -t {shlex.quote(target)}; "
            "printf '%s\\n' destroyed; "
            "else printf '%s\\n' not_found; fi"
        )
        client = self._connect(machine)
        try:
            _, stdout_file, stderr_file = client.exec_command(f"bash -lc {shlex.quote(script)}")
            stdout = stdout_file.read().decode("utf-8", errors="replace").strip()
            stderr = stderr_file.read().decode("utf-8", errors="replace").strip()
            exit_code = stdout_file.channel.recv_exit_status()
            if exit_code != 0:
                raise RuntimeError(stderr or stdout or "terminal destroy failed")
            return {"destroy_result": stdout or "unknown"}
        finally:
            client.close()

    def restart_tmux_server(self, machine: RemoteMachine) -> Dict[str, Any]:
        """Restart the user's remote tmux server through direct SSH."""
        if self._uses_windows_agent(machine):
            raise RuntimeError("tmux server restart is only available for ssh-tmux machines")

        if machine.startup_commands:
            raise RuntimeError("tmux server restart does not yet support startup_commands machines")

        script = (
            "if ! command -v tmux >/dev/null 2>&1; then "
            "printf '%s\\n' missing_tmux; exit 3; "
            "fi; "
            "sessions=$(tmux list-sessions -F '#{session_name}' 2>/dev/null || true); "
            "if [ -n \"$sessions\" ]; then "
            "printf '%s\\n' has_sessions; printf '%s\\n' \"$sessions\"; exit 2; "
            "fi; "
            "if tmux display-message -p '#{pid}' >/dev/null 2>&1; then "
            "old_pid=$(tmux display-message -p '#{pid}' 2>/dev/null || true); "
            "tmux kill-server >/dev/null 2>&1 || true; "
            "printf '%s\\n' restarted; printf '%s\\n' \"$old_pid\"; "
            "else "
            "printf '%s\\n' not_running; "
            "fi"
        )
        client = self._connect(machine)
        try:
            _, stdout_file, stderr_file = client.exec_command(f"bash -lc {shlex.quote(script)}")
            stdout = stdout_file.read().decode("utf-8", errors="replace")
            stderr = stderr_file.read().decode("utf-8", errors="replace").strip()
            exit_code = stdout_file.channel.recv_exit_status()
        finally:
            client.close()

        lines = [line for line in stdout.splitlines() if line.strip()]
        status = lines[0] if lines else "unknown"
        if status == "has_sessions":
            remote_sessions = lines[1:]
            raise RuntimeError(
                "Remote tmux server still has sessions: " + ", ".join(remote_sessions)
            )
        if status == "missing_tmux":
            raise RuntimeError("tmux is not installed on the remote machine")
        if exit_code not in {0, 1}:
            raise RuntimeError(stderr or stdout.strip() or "tmux server restart failed")
        if status == "restarted":
            return {
                "tmux_server_status": "restarted",
                "old_tmux_server_pid": lines[1] if len(lines) > 1 else None,
            }
        if status == "not_running":
            return {"tmux_server_status": "not_running", "old_tmux_server_pid": None}
        raise RuntimeError(stderr or stdout.strip() or "tmux server restart failed")

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
        remote_dir = remote_dir.replace("\\", "/")
        drive_match = re.match(r"^[A-Za-z]:/?$", remote_dir)
        if drive_match:
            return
        drive_prefix = ""
        remainder = remote_dir
        if re.match(r"^[A-Za-z]:/", remote_dir):
            drive_prefix = remote_dir[:2]
            remainder = remote_dir[3:]
            current = drive_prefix + "/"
            for part in [part for part in remainder.split("/") if part]:
                current = current.rstrip("/") + "/" + part
                try:
                    sftp.stat(current)
                except IOError:
                    sftp.mkdir(current)
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
            for dirname in dirs:
                try:
                    sftp.mkdir(posixpath.join(remote_root, dirname))
                except IOError:
                    pass
            for filename in files:
                local_file = os.path.join(root, filename)
                remote_file = posixpath.join(remote_root, filename)
                sftp.put(local_file, remote_file)
                total += os.path.getsize(local_file)
        return total

    def _write_remote_script(
        self,
        sftp: paramiko.SFTPClient,
        remote_path: str,
        content: str,
    ) -> None:
        with sftp.open(remote_path, "w") as remote_file:
            remote_file.write(content)
        try:
            sftp.chmod(remote_path, 0o700)
        except IOError:
            pass

    def _background_worker_script(
        self,
        remote_state_dir: str,
        cwd: str,
        command: str,
    ) -> str:
        return "\n".join(
            [
                "#!/usr/bin/env bash",
                "set +e",
                f"RR_DIR={shlex.quote(remote_state_dir)}",
                f"CWD={shlex.quote(cwd)}",
                f"USER_COMMAND={shlex.quote(command)}",
                'STATUS_FILE="$RR_DIR/status"',
                'EXIT_CODE_FILE="$RR_DIR/exit_code"',
                'ENDED_AT_FILE="$RR_DIR/ended_at"',
                "mark_stopped() {",
                "  printf '%s\\n' stopped > \"$STATUS_FILE\"",
                "  printf '%s\\n' 143 > \"$EXIT_CODE_FILE\"",
                "  date -u +'%Y-%m-%dT%H:%M:%SZ' > \"$ENDED_AT_FILE\"",
                "  exit 143",
                "}",
                "trap mark_stopped TERM INT HUP",
                'cd "$CWD"',
                "cd_rc=$?",
                "if [ \"$cd_rc\" -ne 0 ]; then",
                "  rc=$cd_rc",
                "  printf '%s\\n' \"$rc\" > \"$EXIT_CODE_FILE\"",
                "  date -u +'%Y-%m-%dT%H:%M:%SZ' > \"$ENDED_AT_FILE\"",
                "  printf '%s\\n' failed > \"$STATUS_FILE\"",
                "  exit \"$rc\"",
                "fi",
                'eval "$USER_COMMAND"',
                "rc=$?",
                "printf '%s\\n' \"$rc\" > \"$EXIT_CODE_FILE\"",
                "date -u +'%Y-%m-%dT%H:%M:%SZ' > \"$ENDED_AT_FILE\"",
                "current_status=$(cat \"$STATUS_FILE\" 2>/dev/null || true)",
                "if [ \"$current_status\" != stopped ]; then",
                "  printf '%s\\n' exited > \"$STATUS_FILE\"",
                "fi",
                "exit \"$rc\"",
                "",
            ]
        )

    def _background_launcher_script(
        self,
        remote_state_dir: str,
        remote_worker_file: str,
        remote_stdout_file: str,
        remote_stderr_file: str,
        remote_status_file: str,
        remote_pid_file: str,
    ) -> str:
        return "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -e",
                f"RR_DIR={shlex.quote(remote_state_dir)}",
                f"WORKER={shlex.quote(remote_worker_file)}",
                f"STDOUT_FILE={shlex.quote(remote_stdout_file)}",
                f"STDERR_FILE={shlex.quote(remote_stderr_file)}",
                f"STATUS_FILE={shlex.quote(remote_status_file)}",
                f"PID_FILE={shlex.quote(remote_pid_file)}",
                'mkdir -p "$RR_DIR"',
                ': > "$STDOUT_FILE"',
                ': > "$STDERR_FILE"',
                "printf '%s\\n' running > \"$STATUS_FILE\"",
                "if command -v setsid >/dev/null 2>&1; then",
                '  setsid bash "$WORKER" >> "$STDOUT_FILE" 2>> "$STDERR_FILE" < /dev/null &',
                "else",
                '  nohup bash "$WORKER" >> "$STDOUT_FILE" 2>> "$STDERR_FILE" < /dev/null &',
                "fi",
                "pid=$!",
                "printf '%s\\n' \"$pid\" > \"$PID_FILE\"",
                "printf 'pid=%s\\n' \"$pid\"",
                'printf "state_dir=%s\\n" "$RR_DIR"',
                "",
            ]
        )

    def _parse_background_launch_pid(self, stdout: str) -> str:
        for line in stdout.splitlines():
            if line.startswith("pid="):
                pid = line.split("=", 1)[1].strip()
                if pid:
                    return pid
        raise RuntimeError(f"background launch did not return pid: {stdout.strip()}")

    def _doctor_windows_agent(self, machine: RemoteMachine) -> Dict[str, Any]:
        errors: List[str] = []
        reachable = False
        auth_ok = False
        default_cwd_ok = False
        checked_at = get_timestamp()
        client: Optional[paramiko.SSHClient] = None
        try:
            client = self._connect(machine, timeout=15)
            reachable = True
            auth_ok = True
            script = (
                "$ErrorActionPreference = 'Stop'; "
                f"Set-Location -LiteralPath {self._ps_quote(machine.default_cwd)}; "
                "Get-Command pwsh -ErrorAction Stop | Out-Null; "
                "[pscustomobject]@{cwd=(Get-Location).Path; pwsh=$true} | ConvertTo-Json -Compress"
            )
            stdout, stderr, exit_code = self._run_windows_powershell(client, script, timeout=15)
            default_cwd_ok = exit_code == 0
            if not default_cwd_ok:
                errors.append(stderr or stdout)
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
            "backend": "windows-agent",
            "platform": "windows",
            "errors": [error for error in errors if error],
        }

    def _create_windows_agent_terminal(
        self,
        machine: RemoteMachine,
        cwd: str,
        terminal_id: str,
    ) -> Dict[str, Any]:
        if machine.startup_commands:
            raise RuntimeError("windows-agent backend does not support startup_commands")
        if machine.shell != "pwsh":
            raise RuntimeError("windows-agent backend currently requires shell 'pwsh'")

        agent_dir = self._windows_agent_dir(cwd, terminal_id)
        agent_file = posixpath.join(agent_dir, "windows_agent.py")
        ready_file = posixpath.join(agent_dir, "ready.json")
        transcript_file = posixpath.join(agent_dir, "transcript.txt")
        task_name = self._windows_task_name(terminal_id)
        client = self._connect(machine)
        sftp = client.open_sftp()
        try:
            self._mkdir_p(sftp, agent_dir)
            self._mkdir_p(sftp, posixpath.join(agent_dir, "requests"))
            self._mkdir_p(sftp, posixpath.join(agent_dir, "results"))
            self._write_remote_script(sftp, agent_file, WINDOWS_AGENT_SOURCE)
            script = self._windows_agent_task_script(
                task_name=task_name,
                agent_file=agent_file,
                agent_dir=agent_dir,
                cwd=cwd,
                shell=machine.shell,
            )
            stdout, stderr, exit_code = self._run_windows_powershell(client, script, timeout=30)
            if exit_code != 0:
                raise RuntimeError(stderr or stdout or "Windows agent task start failed")
            ready = self._wait_for_remote_json(sftp, ready_file, timeout=20)
            if ready.get("status") != "ready":
                raise RuntimeError(f"Windows agent did not become ready: {ready}")
            return {
                "backend": "windows-agent",
                "remote_terminal_name": task_name,
                "windows_agent_dir": agent_dir,
                "windows_agent_file": agent_file,
                "windows_agent_ready_file": ready_file,
                "windows_agent_transcript_file": transcript_file,
                "shell": machine.shell,
                "history_limit": None,
                "width": None,
                "height": None,
            }
        finally:
            sftp.close()
            client.close()

    def _start_windows_agent_session_command(
        self,
        machine: RemoteMachine,
        session_record: Dict[str, Any],
        command: str,
        command_id: str,
        cwd: Optional[str],
    ) -> Dict[str, Any]:
        request_id = command_id
        agent_dir = session_record["windows_agent_dir"]
        request_file = posixpath.join(agent_dir, "requests", f"{request_id}.json")
        result_file = posixpath.join(agent_dir, "results", f"{request_id}.json")
        payload = {
            "request_id": request_id,
            "action": "exec",
            "command_id": command_id,
            "command": command,
            "cwd": cwd,
            "timeout": 300,
        }
        client = self._connect(machine)
        sftp = client.open_sftp()
        try:
            self._write_remote_json(sftp, request_file, payload)
        finally:
            sftp.close()
            client.close()
        return {
            "command_backend": "windows-agent",
            "remote_state_dir": agent_dir,
            "windows_request_file": request_file,
            "windows_result_file": result_file,
        }

    def _inspect_windows_agent_session_command(
        self,
        machine: RemoteMachine,
        command_record: Dict[str, Any],
        stdout_limit: int,
        stderr_limit: int,
    ) -> Dict[str, Any]:
        client = self._connect(machine)
        sftp = client.open_sftp()
        try:
            result = self._read_remote_json(
                sftp,
                command_record["windows_result_file"],
                missing_ok=True,
            )
        finally:
            sftp.close()
            client.close()
        if not result:
            return {
                "status": "running",
                "exit_code": None,
                "stdout": "",
                "stderr": "",
                "stdout_truncated": False,
                "stderr_truncated": False,
                "started_at": command_record.get("started_at"),
                "ended_at": None,
            }
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        return {
            "status": result.get("status", "exited"),
            "exit_code": result.get("exit_code"),
            "stdout": stdout[:stdout_limit],
            "stderr": stderr[:stderr_limit],
            "stdout_truncated": len(stdout) > stdout_limit,
            "stderr_truncated": len(stderr) > stderr_limit,
            "started_at": result.get("started_at"),
            "ended_at": result.get("ended_at"),
        }

    def _send_windows_agent_input(
        self,
        machine: RemoteMachine,
        terminal_record: Dict[str, Any],
        input_text: str,
        enter: bool = True,
    ) -> Dict[str, Any]:
        request_id = uuid.uuid4().hex
        agent_dir = terminal_record["windows_agent_dir"]
        request_file = posixpath.join(agent_dir, "requests", f"{request_id}.json")
        result_file = posixpath.join(agent_dir, "results", f"{request_id}.json")
        payload = {
            "request_id": request_id,
            "action": "send",
            "input_text": input_text,
            "enter": enter,
        }
        client = self._connect(machine)
        sftp = client.open_sftp()
        try:
            self._write_remote_json(sftp, request_file, payload)
            result = self._wait_for_remote_json(sftp, result_file, timeout=10)
        finally:
            sftp.close()
            client.close()
        if result.get("status") != "sent":
            raise RuntimeError(result.get("error") or "Windows agent send failed")
        return {"input_sent": True}

    def _capture_windows_agent_terminal(
        self,
        machine: RemoteMachine,
        terminal_record: Dict[str, Any],
    ) -> Dict[str, Any]:
        client = self._connect(machine)
        sftp = client.open_sftp()
        try:
            transcript = self._read_remote_text(
                sftp,
                machine,
                terminal_record["windows_agent_transcript_file"],
                missing_ok=True,
            )
            status_payload = self._read_remote_json(
                sftp,
                posixpath.join(terminal_record["windows_agent_dir"], "status.json"),
                missing_ok=True,
            )
        finally:
            sftp.close()
            client.close()
        status = "active"
        if status_payload and status_payload.get("status") == "stopped":
            status = "destroyed"
        return {"status": status, "transcript": transcript}

    def _destroy_windows_agent_terminal(
        self,
        machine: RemoteMachine,
        terminal_record: Dict[str, Any],
    ) -> Dict[str, Any]:
        request_id = uuid.uuid4().hex
        agent_dir = terminal_record["windows_agent_dir"]
        request_file = posixpath.join(agent_dir, "requests", f"{request_id}.json")
        result_file = posixpath.join(agent_dir, "results", f"{request_id}.json")
        status_file = posixpath.join(agent_dir, "status.json")
        client = self._connect(machine)
        sftp = client.open_sftp()
        try:
            self._write_remote_json(
                sftp,
                request_file,
                {"request_id": request_id, "action": "destroy"},
            )
            self._wait_for_remote_json(sftp, result_file, timeout=10)
            deadline = time.time() + 10
            while time.time() < deadline:
                status = self._read_remote_json(sftp, status_file, missing_ok=True)
                if status and status.get("status") == "stopped":
                    break
                time.sleep(0.2)
            script = self._windows_delete_task_script(terminal_record["remote_terminal_name"])
            self._run_windows_powershell(client, script, timeout=15)
        finally:
            sftp.close()
            client.close()
        return {"destroy_result": "destroyed"}

    def _windows_agent_dir(self, cwd: str, terminal_id: str) -> str:
        normalized_cwd = cwd.replace("\\", "/").rstrip("/")
        return posixpath.join(normalized_cwd, ".remote-runner", "windows-agent", terminal_id)

    def _windows_task_name(self, terminal_id: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", terminal_id)
        return f"RemoteRunner_{safe}"

    def _windows_agent_task_script(
        self,
        task_name: str,
        agent_file: str,
        agent_dir: str,
        cwd: str,
        shell: str,
    ) -> str:
        argument = (
            f'"{agent_file}" run-session '
            f'--session-dir "{agent_dir}" '
            f'--cwd "{cwd}" '
            f'--shell "{shell}"'
        )
        return "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                f"$taskName = {self._ps_quote(task_name)}",
                f"$argument = {self._ps_quote(argument)}",
                "$action = New-ScheduledTaskAction -Execute 'python' -Argument $argument",
                "$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddYears(1)",
                "Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Force | Out-Null",
                "Start-ScheduledTask -TaskName $taskName",
                "[pscustomobject]@{task=$taskName; started=$true} | ConvertTo-Json -Compress",
            ]
        )

    def _windows_delete_task_script(self, task_name: str) -> str:
        return "\n".join(
            [
                "$ErrorActionPreference = 'SilentlyContinue'",
                f"$taskName = {self._ps_quote(task_name)}",
                "Stop-ScheduledTask -TaskName $taskName | Out-Null",
                "Unregister-ScheduledTask -TaskName $taskName -Confirm:$false | Out-Null",
                "[pscustomobject]@{task=$taskName; deleted=$true} | ConvertTo-Json -Compress",
            ]
        )

    def _run_windows_powershell(
        self,
        client: paramiko.SSHClient,
        script: str,
        timeout: int = 30,
    ) -> tuple[str, str, int]:
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        command = f"powershell -NoProfile -EncodedCommand {encoded}"
        _, stdout_file, stderr_file = client.exec_command(command, timeout=timeout)
        stdout = stdout_file.read().decode("utf-8", errors="replace")
        stderr = stderr_file.read().decode("utf-8", errors="replace")
        exit_code = stdout_file.channel.recv_exit_status()
        return stdout, stderr, exit_code

    def _ps_quote(self, value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    def _write_remote_json(
        self,
        sftp: paramiko.SFTPClient,
        remote_path: str,
        payload: Dict[str, Any],
    ) -> None:
        self._mkdir_parent(sftp, remote_path)
        data = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        tmp_path = f"{remote_path}.tmp-{uuid.uuid4().hex}"
        with sftp.open(tmp_path, "w") as remote_file:
            remote_file.write(data)
        sftp.rename(tmp_path, remote_path)

    def _read_remote_json(
        self,
        sftp: paramiko.SFTPClient,
        remote_path: str,
        missing_ok: bool = False,
    ) -> Optional[Dict[str, Any]]:
        try:
            with sftp.open(remote_path, "rb") as remote_file:
                data = remote_file.read()
        except IOError:
            if missing_ok:
                return None
            raise
        if isinstance(data, str):
            text = data
        else:
            text = data.decode("utf-8", errors="replace")
        if not text.strip():
            return None
        return json.loads(text)

    def _wait_for_remote_json(
        self,
        sftp: paramiko.SFTPClient,
        remote_path: str,
        timeout: int,
    ) -> Dict[str, Any]:
        deadline = time.time() + max(0, timeout)
        while time.time() < deadline:
            payload = self._read_remote_json(sftp, remote_path, missing_ok=True)
            if payload is not None:
                return payload
            time.sleep(0.2)
        raise TimeoutError(f"Timed out waiting for remote JSON: {remote_path}")

    def _read_remote_text(
        self,
        sftp: paramiko.SFTPClient,
        machine: RemoteMachine,
        remote_path: str,
        missing_ok: bool = False,
    ) -> str:
        sftp_path = machine.map_file_path(remote_path)
        try:
            with sftp.open(sftp_path, "rb") as remote_file:
                data = remote_file.read()
        except IOError:
            if missing_ok:
                return ""
            raise
        if isinstance(data, str):
            return data
        return data.decode("utf-8", errors="replace")

    def _read_remote_text_limited(
        self,
        sftp: paramiko.SFTPClient,
        machine: RemoteMachine,
        remote_path: str,
        limit: int,
    ) -> tuple[str, bool]:
        sftp_path = machine.map_file_path(remote_path)
        read_limit = max(0, limit) + 1
        try:
            with sftp.open(sftp_path, "rb") as remote_file:
                data = remote_file.read(read_limit)
        except IOError:
            return "", False
        if isinstance(data, str):
            raw = data.encode("utf-8", errors="replace")
        else:
            raw = data
        truncated = len(raw) > max(0, limit)
        raw = raw[: max(0, limit)]
        return raw.decode("utf-8", errors="replace"), truncated

    def _remote_pid_alive(self, client: paramiko.SSHClient, pid: Optional[str]) -> bool:
        if not pid:
            return False
        command = f"kill -0 {shlex.quote(str(pid))} >/dev/null 2>&1"
        _, stdout_file, _ = client.exec_command(command)
        return stdout_file.channel.recv_exit_status() == 0

    def _tmux_session_name(self, terminal_id: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", terminal_id)
        return f"rr_{safe}"

    def _session_command_paths(self, session_cwd: str, command_id: str) -> Dict[str, str]:
        remote_state_dir = posixpath.join(session_cwd, ".remote-runner", "commands", command_id)
        return {
            "remote_state_dir": remote_state_dir,
            "remote_stdout_file": posixpath.join(remote_state_dir, "stdout.log"),
            "remote_stderr_file": posixpath.join(remote_state_dir, "stderr.log"),
            "remote_status_file": posixpath.join(remote_state_dir, "status"),
            "remote_exit_code_file": posixpath.join(remote_state_dir, "exit_code"),
            "remote_started_at_file": posixpath.join(remote_state_dir, "started_at"),
            "remote_ended_at_file": posixpath.join(remote_state_dir, "ended_at"),
            "remote_wrapper_file": posixpath.join(remote_state_dir, "run.sh"),
        }

    def _session_command_wrapper_script(
        self,
        paths: Dict[str, str],
        command: str,
        command_id: str,
        cwd: Optional[str],
        cwd_override: bool,
    ) -> str:
        begin_marker = f"__REMOTE_RUNNER_CMD_BEGIN_{command_id}__"
        end_marker = f"__REMOTE_RUNNER_CMD_END_{command_id}__"
        lines = [
            "# Remote Runner persistent session command wrapper. Must be sourced in bash.",
            "set +e",
            f"__rr_dir={shlex.quote(paths['remote_state_dir'])}",
            f"__rr_stdout={shlex.quote(paths['remote_stdout_file'])}",
            f"__rr_stderr={shlex.quote(paths['remote_stderr_file'])}",
            f"__rr_status={shlex.quote(paths['remote_status_file'])}",
            f"__rr_exit_code={shlex.quote(paths['remote_exit_code_file'])}",
            f"__rr_started_at={shlex.quote(paths['remote_started_at_file'])}",
            f"__rr_ended_at={shlex.quote(paths['remote_ended_at_file'])}",
            f"__rr_command={shlex.quote(command)}",
            f"__rr_cwd={shlex.quote(cwd or '')}",
            f"__rr_cwd_override={'1' if cwd_override else '0'}",
            "mkdir -p \"$__rr_dir\"",
            ": > \"$__rr_stdout\"",
            ": > \"$__rr_stderr\"",
            "printf '%s\\n' running > \"$__rr_status\"",
            "date -u +'%Y-%m-%dT%H:%M:%SZ' > \"$__rr_started_at\"",
            f"printf '\\n{begin_marker}\\n'",
            "__rr_stopped=0",
            "trap '__rr_stopped=1' INT TERM",
            "if [ \"$__rr_cwd_override\" = 1 ]; then",
            "  cd \"$__rr_cwd\"",
            "  __rr_cd_rc=$?",
            "  if [ \"$__rr_cd_rc\" -ne 0 ]; then",
            "    printf 'cd failed: %s\\n' \"$__rr_cwd\" | tee -a \"$__rr_stderr\" >&2",
            "    __rr_rc=$__rr_cd_rc",
            "    printf '%s\\n' \"$__rr_rc\" > \"$__rr_exit_code\"",
            "    date -u +'%Y-%m-%dT%H:%M:%SZ' > \"$__rr_ended_at\"",
            "    printf '%s\\n' failed > \"$__rr_status\"",
            f"    printf '\\n{end_marker}:%s\\n' \"$__rr_rc\"",
            "    trap - INT TERM",
            "    return \"$__rr_rc\" 2>/dev/null || exit \"$__rr_rc\"",
            "  fi",
            "fi",
            "{ eval \"$__rr_command\"; } > >(tee -a \"$__rr_stdout\") 2> >(tee -a \"$__rr_stderr\" >&2)",
            "__rr_rc=$?",
            "__rr_existing_status=$(cat \"$__rr_status\" 2>/dev/null || true)",
            "if [ \"$__rr_existing_status\" = stopped ] || [ \"$__rr_stopped\" = 1 ] || [ \"$__rr_rc\" -eq 130 ] || [ \"$__rr_rc\" -eq 143 ]; then",
            "  __rr_status_value=stopped",
            "  __rr_rc=143",
            "else",
            "  __rr_status_value=exited",
            "fi",
            f"printf '\\n{end_marker}:%s\\n' \"$__rr_rc\"",
            "printf '%s\\n' \"$__rr_rc\" > \"$__rr_exit_code\"",
            "date -u +'%Y-%m-%dT%H:%M:%SZ' > \"$__rr_ended_at\"",
            "printf '%s\\n' \"$__rr_status_value\" > \"$__rr_status\"",
            "trap - INT TERM",
            "return \"$__rr_rc\" 2>/dev/null || exit \"$__rr_rc\"",
            "",
        ]
        return "\n".join(lines)

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
