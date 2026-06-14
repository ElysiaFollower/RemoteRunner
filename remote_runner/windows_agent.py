"""Embedded Windows agent used by the Windows PowerShell backend."""

WINDOWS_AGENT_SOURCE = r'''
import argparse
import base64
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone


def utc_timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path, payload):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, path)


def append_text(path, text):
    with open(path, "a", encoding="utf-8", errors="replace") as f:
        f.write(text)


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def command_to_base64(command):
    return base64.b64encode(command.encode("utf-8")).decode("ascii")


class PowerShellSession:
    def __init__(self, session_dir, cwd, shell):
        self.session_dir = session_dir
        self.cwd = cwd
        self.shell = shell
        self.transcript_file = os.path.join(session_dir, "transcript.txt")
        self.output_queue = queue.Queue()
        self.process = None
        self.reader = None

    def start(self):
        shell_path = shutil.which(self.shell) or self.shell
        self.process = subprocess.Popen(
            [shell_path, "-NoLogo", "-NoProfile", "-NoExit"],
            cwd=self.cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self.reader = threading.Thread(target=self._read_output, daemon=True)
        self.reader.start()
        self._send_line("[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)")
        self._send_line("$OutputEncoding = [Console]::OutputEncoding")
        self._send_line("Set-Location -LiteralPath " + ps_quote(self.cwd))
        self._send_line("$ProgressPreference = 'SilentlyContinue'")

    def _read_output(self):
        assert self.process is not None
        assert self.process.stdout is not None
        for line in self.process.stdout:
            append_text(self.transcript_file, line)
            self.output_queue.put(line)

    def _send_line(self, line):
        assert self.process is not None
        assert self.process.stdin is not None
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()

    def _drain_output(self):
        while True:
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                return

    def execute(self, command, command_id, cwd=None, timeout=300):
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError("PowerShell session is not running")

        begin_marker = "__REMOTE_RUNNER_WIN_BEGIN_%s__" % command_id
        end_marker = "__REMOTE_RUNNER_WIN_END_%s__" % command_id
        encoded_command = command_to_base64(command)
        started_at = utc_timestamp()
        self._drain_output()

        lines = ["Write-Output " + ps_quote(begin_marker), "$global:LASTEXITCODE = $null"]
        if cwd:
            lines.append("Set-Location -LiteralPath " + ps_quote(cwd))
        lines.extend(
            [
                "$__rr_success = $true",
                "try { $__rr_command = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String(" + ps_quote(encoded_command) + ")); $__rr_script = [ScriptBlock]::Create($__rr_command); . $__rr_script; $__rr_success = $? } catch { Write-Error $_; $__rr_success = $false }",
                "$__rr_native = $global:LASTEXITCODE",
                "if ($null -ne $__rr_native) { $__rr_rc = [int]$__rr_native } elseif ($__rr_success) { $__rr_rc = 0 } else { $__rr_rc = 1 }",
                "Write-Output ((" + ps_quote(end_marker + ":") + ") + $__rr_rc)",
            ]
        )

        self._send_line("; ".join(lines))

        deadline = time.time() + max(0, timeout)
        selected = []
        in_command = False
        exit_code = None
        while time.time() < deadline:
            try:
                line = self.output_queue.get(timeout=0.1)
            except queue.Empty:
                if self.process.poll() is not None:
                    break
                continue
            stripped = line.strip()
            if begin_marker in stripped and "Write-Output" not in stripped:
                in_command = True
                continue
            if end_marker + ":" in stripped and "Write-Output" not in stripped:
                try:
                    exit_code = int(stripped.rsplit(":", 1)[1])
                except ValueError:
                    exit_code = 1
                break
            if in_command:
                selected.append(line)

        if exit_code is None:
            raise TimeoutError("Windows PowerShell command did not finish before timeout")

        ended_at = utc_timestamp()
        return {
            "status": "exited",
            "exit_code": exit_code,
            "stdout": "".join(selected),
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
            "started_at": started_at,
            "ended_at": ended_at,
        }

    def send(self, input_text, enter=True):
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError("PowerShell session is not running")
        if enter:
            self._send_line(input_text)
        else:
            assert self.process.stdin is not None
            self.process.stdin.write(input_text)
            self.process.stdin.flush()

    def stop(self):
        if self.process is None:
            return
        if self.process.poll() is None:
            try:
                self._send_line("exit")
                self.process.wait(timeout=3)
            except Exception:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except Exception:
                    self.process.kill()


class Agent:
    def __init__(self, session_dir, cwd, shell):
        self.session_dir = session_dir
        self.cwd = cwd
        self.shell = shell
        self.requests_dir = os.path.join(session_dir, "requests")
        self.results_dir = os.path.join(session_dir, "results")
        self.ready_file = os.path.join(session_dir, "ready.json")
        self.status_file = os.path.join(session_dir, "status.json")
        self.stop_file = os.path.join(session_dir, "stop")
        self.seen = set()
        self.ps = PowerShellSession(session_dir, cwd, shell)

    def start(self):
        ensure_dir(self.requests_dir)
        ensure_dir(self.results_dir)
        ensure_dir(self.session_dir)
        open(os.path.join(self.session_dir, "transcript.txt"), "a", encoding="utf-8").close()
        self.ps.start()
        payload = {
            "status": "ready",
            "pid": os.getpid(),
            "cwd": self.cwd,
            "shell": self.shell,
            "ready_at": utc_timestamp(),
        }
        write_json(self.ready_file, payload)
        write_json(self.status_file, payload)

    def run(self):
        self.start()
        try:
            while not os.path.exists(self.stop_file):
                try:
                    self._process_requests()
                except Exception:
                    append_text(
                        os.path.join(self.session_dir, "agent-error.log"),
                        traceback.format_exc() + "\n",
                    )
                time.sleep(0.1)
        finally:
            self.ps.stop()
            write_json(
                self.status_file,
                {
                    "status": "stopped",
                    "pid": os.getpid(),
                    "stopped_at": utc_timestamp(),
                },
            )

    def _process_requests(self):
        for name in sorted(os.listdir(self.requests_dir)):
            if not name.endswith(".json") or name in self.seen:
                continue
            path = os.path.join(self.requests_dir, name)
            request = read_json(path, default=None)
            if request is None:
                continue
            self.seen.add(name)
            request_id = request.get("request_id") or os.path.splitext(name)[0]
            result_path = os.path.join(self.results_dir, request_id + ".json")
            try:
                result = self._handle_request(request)
            except Exception as exc:
                result = {
                    "status": "failed",
                    "exit_code": None,
                    "stdout": "",
                    "stderr": str(exc),
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                    "started_at": utc_timestamp(),
                    "ended_at": utc_timestamp(),
                }
            write_json(result_path, result)

    def _handle_request(self, request):
        action = request.get("action")
        if action == "exec":
            return self.ps.execute(
                request.get("command") or "",
                request.get("command_id") or request.get("request_id") or uuid.uuid4().hex,
                cwd=request.get("cwd"),
                timeout=int(request.get("timeout") or 300),
            )
        if action == "send":
            self.ps.send(request.get("input_text") or "", enter=bool(request.get("enter", True)))
            return {
                "status": "sent",
                "input_sent": True,
                "started_at": utc_timestamp(),
                "ended_at": utc_timestamp(),
            }
        if action == "destroy":
            open(self.stop_file, "w", encoding="utf-8").write("stop")
            return {
                "status": "destroying",
                "destroy_result": "requested",
                "started_at": utc_timestamp(),
                "ended_at": utc_timestamp(),
            }
        raise ValueError("unknown request action: %s" % action)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    run_session = sub.add_parser("run-session")
    run_session.add_argument("--session-dir", required=True)
    run_session.add_argument("--cwd", required=True)
    run_session.add_argument("--shell", default="pwsh")
    args = parser.parse_args()
    if args.command == "run-session":
        Agent(args.session_dir, args.cwd, args.shell).run()


if __name__ == "__main__":
    main()
'''
