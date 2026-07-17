import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional


def run_cli(
    arguments: List[str],
    *,
    environment: Dict[str, str],
    stdin: Optional[bytes] = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "remote_runner.cli", *arguments],
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        check=False,
    )


def test_cli_defaults_read_and_tail_to_raw_terminal_bytes(
    rr_env: Dict[str, Any], cli_env: Dict[str, str], wait_for_output
) -> None:
    created = run_cli(
        ["session", "create", "--name", "cli-shell", "--shell", rr_env["shell"]],
        environment=cli_env,
    )
    assert created.returncode == 0
    created_json = json.loads(created.stdout)

    sent = run_cli(
        ["session", "send", "--session", "cli-shell", "--input", "printf 'CLI_VISIBLE\\n'"],
        environment=cli_env,
    )
    assert sent.returncode == 0
    sent_json = json.loads(sent.stdout)
    assert set(sent_json) == {"session_name", "read_from_cursor"}
    assert "input" not in sent_json
    wait_for_output(rr_env["manager"], "cli-shell", b"CLI_VISIBLE")

    raw = run_cli(
        ["session", "tail", "--session", "cli-shell", "--bytes", "4096"],
        environment=cli_env,
    )
    assert raw.returncode == 0
    assert b"CLI_VISIBLE" in raw.stdout
    assert not raw.stdout.lstrip().startswith(b"{")

    structured = run_cli(
        ["session", "tail", "--session", "cli-shell", "--bytes", "4096", "--json"],
        environment=cli_env,
    )
    structured_json = json.loads(structured.stdout)
    assert set(structured_json) == {
        "output",
        "output_start_cursor",
        "transcript_end_cursor",
    }
    assert "CLI_VISIBLE" in structured_json["output"]
    assert Path(created_json["transcript_path"]).exists()


def test_cli_show_is_the_only_state_query(rr_env: Dict[str, Any], cli_env: Dict[str, str]) -> None:
    created = run_cli(
        ["session", "create", "--name", "state-shell", "--shell", rr_env["shell"]],
        environment=cli_env,
    )
    assert created.returncode == 0

    shown = run_cli(
        ["session", "show", "--session", "state-shell"],
        environment=cli_env,
    )
    state = json.loads(shown.stdout)
    assert state["session_name"] == "state-shell"
    assert "time_since_last_output_ms" in state
    assert "transcript_path" in state

    read = run_cli(
        ["session", "read", "--session", "state-shell", "--json"],
        environment=cli_env,
    )
    read_json = json.loads(read.stdout)
    assert "session_status" not in read_json
    assert "last_output_at" not in read_json


def test_cli_tool_errors_are_structured_on_stderr(cli_env: Dict[str, str]) -> None:
    missing = run_cli(
        ["session", "show", "--session", "missing"],
        environment=cli_env,
    )
    assert missing.returncode == 1
    assert missing.stdout == b""
    error = json.loads(missing.stderr)
    assert error["error"]["code"] == "session_not_found"
    assert "message" in error["error"]

    usage = run_cli(["session", "send"], environment=cli_env)
    assert usage.returncode == 2
    assert usage.stdout == b""
    assert json.loads(usage.stderr)["error"]["code"] == "invalid_usage"


def test_cli_has_no_legacy_backend_commands(cli_env: Dict[str, str]) -> None:
    for command in (["machine", "list"], ["file", "list"], ["run", "list"]):
        result = run_cli(command, environment=cli_env)
        assert result.returncode == 2
        assert json.loads(result.stderr)["error"]["code"] == "invalid_usage"

    interrupt = run_cli(
        ["session", "interrupt", "--session", "anything"],
        environment=cli_env,
    )
    assert interrupt.returncode == 2
    assert json.loads(interrupt.stderr)["error"]["code"] == "invalid_usage"


def test_cli_stdin_is_one_line_and_json_read_has_only_range_fields(
    rr_env: Dict[str, Any], cli_env: Dict[str, str], wait_for_output
) -> None:
    created = run_cli(
        ["session", "create", "--name", "stdin-shell", "--shell", rr_env["shell"]],
        environment=cli_env,
    )
    assert created.returncode == 0
    sent = run_cli(
        ["session", "send", "--session", "stdin-shell", "--stdin"],
        environment=cli_env,
        stdin=b"printf 'STDIN_VISIBLE\\n'\n",
    )
    assert sent.returncode == 0
    assert set(json.loads(sent.stdout)) == {"session_name", "read_from_cursor"}
    wait_for_output(rr_env["manager"], "stdin-shell", b"STDIN_VISIBLE")

    read = run_cli(
        [
            "session",
            "read",
            "--session",
            "stdin-shell",
            "--from",
            "0",
            "--max-bytes",
            "4096",
            "--json",
        ],
        environment=cli_env,
    )
    assert read.returncode == 0
    assert set(json.loads(read.stdout)) == {
        "output",
        "next_read_cursor",
        "transcript_end_cursor",
    }


def test_cli_help_exposes_only_instance_and_session_resources(cli_env: Dict[str, str]) -> None:
    result = run_cli(["--help"], environment=cli_env)

    assert result.returncode == 0
    assert b"instance" in result.stdout
    assert b"session" in result.stdout
    assert b"machine" not in result.stdout
    assert b"artifact" not in result.stdout
