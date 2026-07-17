"""The single terminal implementation: a local tmux pane and raw transcript."""

import os
from pathlib import Path
import pwd
import re
import shlex
import shutil
import subprocess
import sys
import time
from typing import List, Optional
import uuid

from remote_runner.errors import TmuxError

KEY_PATTERN = re.compile(
    r"^(?:C-|M-|S-)?(?:[A-Za-z0-9]|Space|Tab|Enter|Escape|BSpace|DC|Home|End|Up|Down|Left|Right|PageUp|PageDown|F(?:[1-9]|1[0-2]))$"
)


class TmuxTerminal:
    """Hide tmux process details behind one small persistent-terminal interface."""

    def __init__(self, *, binary: Optional[str] = None, socket_name: Optional[str] = None) -> None:
        configured_binary = os.environ.get("REMOTE_RUNNER_TMUX_BINARY")
        self.binary = binary or configured_binary or shutil.which("tmux") or "tmux"
        self.socket_name = socket_name or os.environ.get("REMOTE_RUNNER_TMUX_SOCKET")

    def ensure_supported(self) -> None:
        if sys.platform not in {"darwin", "linux"}:
            raise TmuxError(
                "unsupported_platform",
                "Remote Runner requires macOS or Linux with local tmux",
            )
        resolved = shutil.which(self.binary) if os.path.sep not in self.binary else self.binary
        if not resolved or not os.path.isfile(resolved) or not os.access(resolved, os.X_OK):
            raise TmuxError(
                "tmux_unavailable",
                "Remote Runner requires an executable local tmux binary",
            )
        self.binary = resolved
        self._run(["-V"])

    def create(
        self,
        *,
        tmux_session_name: str,
        transcript_path: Path,
        cwd: Path,
        shell_path: Optional[str] = None,
        width: int = 120,
        height: int = 40,
    ) -> str:
        self.ensure_supported()
        if self.session_exists(tmux_session_name):
            raise TmuxError(
                "tmux_name_in_use",
                f"tmux Session '{tmux_session_name}' already exists",
                context={"tmux_session_name": tmux_session_name},
            )
        if not cwd.is_dir():
            raise TmuxError("cwd_not_found", f"Session cwd '{cwd}' is not a directory")
        shell = self.resolve_shell(shell_path)
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        transcript_path.touch(mode=0o600, exist_ok=True)
        os.chmod(transcript_path, 0o600)

        pending, release = self._startup_paths(transcript_path.parent)
        for marker in (pending, release):
            if marker.exists():
                marker.unlink()
        pending.touch(mode=0o600, exist_ok=False)
        start_script = (
            f"while [ ! -e {shlex.quote(str(release))} ]; do sleep 0.01; done; "
            f"rm -f {shlex.quote(str(release))} {shlex.quote(str(pending))}; "
            f"exec {shlex.quote(shell)} -l"
        )
        shell_command = shlex.join(["/bin/sh", "-c", start_script])
        pane_id: Optional[str] = None
        try:
            created = self._run(
                [
                    "new-session",
                    "-d",
                    "-P",
                    "-F",
                    "#{pane_id}",
                    "-s",
                    tmux_session_name,
                    "-x",
                    str(int(width)),
                    "-y",
                    str(int(height)),
                    "-c",
                    str(cwd),
                    shell_command,
                ]
            )
            pane_id = created.stdout.decode("utf-8", errors="replace").strip()
            if not pane_id.startswith("%"):
                raise TmuxError(
                    "tmux_create_failed",
                    "tmux did not return the created pane id",
                    context={"tmux_session_name": tmux_session_name},
                )
            pipe_command = f"cat >> {shlex.quote(str(transcript_path))}"
            self._run(["pipe-pane", "-O", "-t", pane_id, pipe_command])
            if not self.finish_startup(pane_id, transcript_path.parent):
                raise TmuxError(
                    "shell_start_failed",
                    "The tmux pane did not start the configured shell",
                    context={"tmux_session_name": tmux_session_name},
                )
            return pane_id
        except Exception:
            if self.session_exists(tmux_session_name):
                self._run(["kill-session", "-t", tmux_session_name], check=False)
            self.cleanup_startup(transcript_path.parent)
            raise

    def send_line(self, pane_id: str, text: str) -> None:
        if "\n" in text or "\r" in text:
            raise TmuxError(
                "multiline_input",
                "send accepts exactly one terminal line; use separate send calls",
            )
        buffer_name = f"rr_{uuid.uuid4().hex}"
        loaded = False
        try:
            self._run(
                ["load-buffer", "-b", buffer_name, "-"],
                input_bytes=text.encode("utf-8"),
            )
            loaded = True
            self._run(["paste-buffer", "-d", "-b", buffer_name, "-t", pane_id])
            loaded = False
            self._run(["send-keys", "-t", pane_id, "C-m"])
        finally:
            if loaded:
                self._run(["delete-buffer", "-b", buffer_name], check=False)

    def send_key(self, pane_id: str, key: str) -> None:
        if not KEY_PATTERN.fullmatch(key):
            raise TmuxError(
                "invalid_key",
                f"Unsupported terminal key '{key}'",
                context={"key": key},
            )
        self._run(["send-keys", "-t", pane_id, key])

    def pane_exists(self, pane_id: str) -> bool:
        result = self._run(
            ["display-message", "-p", "-t", pane_id, "#{pane_id}"],
            check=False,
        )
        return result.returncode == 0 and result.stdout.decode().strip() == pane_id

    def recorder_exists(self, pane_id: str) -> bool:
        result = self._run(
            ["display-message", "-p", "-t", pane_id, "#{pane_pipe}"],
            check=False,
        )
        return result.returncode == 0 and result.stdout.decode().strip() == "1"

    def is_healthy(self, pane_id: str) -> bool:
        return self.pane_exists(pane_id) and self.recorder_exists(pane_id)

    def finish_startup(self, pane_id: str, session_dir: Path, timeout: float = 5.0) -> bool:
        pending, release = self._startup_paths(session_dir)
        if pending.exists():
            if not self.is_healthy(pane_id):
                return False
            release.touch(mode=0o600, exist_ok=True)
            deadline = time.monotonic() + timeout
            while pending.exists() and time.monotonic() < deadline:
                if not self.is_healthy(pane_id):
                    return False
                time.sleep(0.01)
        if release.exists() and not pending.exists():
            release.unlink()
        return not pending.exists() and self.is_healthy(pane_id)

    @staticmethod
    def cleanup_startup(session_dir: Path) -> None:
        for marker in TmuxTerminal._startup_paths(session_dir):
            if marker.exists():
                marker.unlink()

    @staticmethod
    def _startup_paths(session_dir: Path) -> tuple[Path, Path]:
        return session_dir / "shell-start.pending", session_dir / "shell-start.release"

    def session_exists(self, tmux_session_name: str) -> bool:
        result = self._run(["has-session", "-t", tmux_session_name], check=False)
        return result.returncode == 0

    def pane_id_for_session(self, tmux_session_name: str) -> Optional[str]:
        result = self._run(
            ["list-panes", "-t", tmux_session_name, "-F", "#{pane_id}"],
            check=False,
        )
        if result.returncode != 0:
            return None
        pane_ids = result.stdout.decode("utf-8", errors="replace").splitlines()
        if len(pane_ids) != 1 or not pane_ids[0].startswith("%"):
            return None
        return str(pane_ids[0])

    def destroy(self, tmux_session_name: str) -> None:
        result = self._run(["kill-session", "-t", tmux_session_name], check=False)
        if result.returncode != 0 and self.session_exists(tmux_session_name):
            self._raise_command_error(result)

    def attach_argv(self, tmux_session_name: str) -> List[str]:
        return self._command(["attach-session", "-t", tmux_session_name])

    def resolve_shell(self, requested: Optional[str]) -> str:
        candidate = requested or os.environ.get("SHELL") or pwd.getpwuid(os.getuid()).pw_shell
        resolved = shutil.which(candidate) if os.path.sep not in candidate else candidate
        if not resolved or not os.path.isfile(resolved) or not os.access(resolved, os.X_OK):
            raise TmuxError("shell_unavailable", f"Shell '{candidate}' is not executable")
        return os.path.abspath(resolved)

    def _command(self, args: List[str]) -> List[str]:
        command = [self.binary]
        if self.socket_name:
            command.extend(["-L", self.socket_name])
        command.extend(args)
        return command

    def _run(
        self,
        args: List[str],
        *,
        input_bytes: Optional[bytes] = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        try:
            result = subprocess.run(
                self._command(args),
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        except OSError as error:
            raise TmuxError("tmux_unavailable", f"Could not execute local tmux: {error}") from error
        if check and result.returncode != 0:
            self._raise_command_error(result)
        return result

    @staticmethod
    def _raise_command_error(result: subprocess.CompletedProcess) -> None:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        if not message:
            message = result.stdout.decode("utf-8", errors="replace").strip()
        raise TmuxError("tmux_command_failed", message or "Local tmux command failed")
