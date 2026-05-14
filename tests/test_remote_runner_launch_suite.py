"""Reusable launch acceptance suite for Remote Runner."""

import os

import pytest

from tests.remote_runner_launch_support import (
    assert_launch_public_contract,
    run_fake_launch_smoke,
    run_real_launch_smoke,
)


@pytest.fixture
def launch_state_dir(tmp_path, monkeypatch):
    state_dir = tmp_path / "launch-state"
    monkeypatch.setenv("REMOTE_RUNNER_STATE_DIR", str(state_dir))
    return state_dir


def test_launch_suite_public_contract():
    assert_launch_public_contract()


def test_launch_suite_fake_core_smoke(launch_state_dir, tmp_path):
    result = run_fake_launch_smoke(tmp_path)

    assert result["doctor"]["reachable"] is True
    assert result["doctor"]["auth_ok"] is True
    assert result["session"]["cwd"] == "/srv/app"
    assert result["exec"]["exit_code"] == 0
    assert "launch-ready" in result["exec"]["stdout"]
    assert result["background"]["status"] == "running"
    assert result["background"]["command_id"].startswith("cmd_")
    assert result["background"]["remote_stdout_file"].endswith("/stdout.log")
    assert result["background"]["remote_status_file"].endswith("/status")
    assert result["background_show"]["stdout"] == "launch-background-started\n"
    assert result["background_stop"]["status"] == "stopped"
    assert result["session_pwd"]["stdout"] == "/srv/app/subdir\n"
    assert result["session_token"]["stdout"] == "launch-session\n"
    assert "/srv/app/subdir" in result["session_read"]["transcript"]
    assert "launch-session" in result["session_read"]["transcript"]
    assert result["put"]["status"] == "completed"
    assert result["download"] == "launch input\n"
    assert any(entry["name"] == "launch_input.txt" for entry in result["list"]["entries"])
    assert result["run"]["status"] == "succeeded"
    assert result["run"]["destroy_session_result"]["status"] == "destroyed"
    assert result["run_output"] == "launch artifact\n"
    assert result["destroyed"]["status"] == "destroyed"
    assert result["machine_state"]["password"] == "***REDACTED***"
    assert result["machine_state"]["path_mappings"] == [
        {"command_prefix": "/srv/app", "file_prefix": "C:/srv/app"}
    ]
    assert (
        result["machine_state_record"]["machines"]["launch-lab-01"]["password"] == "launch-secret"
    )
    assert result["backend_puts"][0]["file_path"] == "C:/srv/app/launch_input.txt"
    assert result["backend_gets"][0]["file_path"] == "C:/srv/app/launch_input.txt"
    assert result["backend_lists"][0]["file_path"] == "C:/srv/app"
    assert any(entry["path"] == "/srv/app/launch_input.txt" for entry in result["list"]["entries"])
    assert len(result["transfer_records"]) == 3
    assert result["session_state"]["status"] == "destroyed"
    assert result["run_state"]["status"] == "succeeded"
    assert result["artifact_manifest"]["artifacts"][0]["local_path"].endswith(
        "launch_run_output.txt"
    )


@pytest.mark.skipif(
    os.environ.get("REMOTE_RUNNER_RUN_REAL_TESTS") != "1",
    reason="Set REMOTE_RUNNER_RUN_REAL_TESTS=1 to run real Remote Runner launch smoke",
)
def test_launch_suite_real_machine_smoke(tmp_path):
    machine_id = os.environ.get("REMOTE_RUNNER_REAL_MACHINE")
    remote_cwd = os.environ.get("REMOTE_RUNNER_REAL_TEST_CWD")
    if not machine_id:
        pytest.skip("REMOTE_RUNNER_REAL_MACHINE is required for real launch smoke")
    if not remote_cwd:
        pytest.skip("REMOTE_RUNNER_REAL_TEST_CWD is required for real launch smoke")

    result = run_real_launch_smoke(machine_id, remote_cwd, tmp_path)

    assert result["doctor"]["reachable"] is True
    assert result["doctor"]["auth_ok"] is True
    assert result["doctor"]["default_cwd_ok"] is True
    assert result["session"]["cwd"] == remote_cwd.rstrip("/")
    assert result["exec"]["exit_code"] == 0
    assert "launch-ready" in result["exec"]["stdout"]
    assert result["put"]["status"] == "completed"
    assert result["download"] == result["run_input"]
    assert any(entry["name"] == result["probe_name"] for entry in result["listing"]["entries"])
    assert result["get"]["status"] == "completed"
    assert result["run"]["status"] == "succeeded"
    assert result["run"]["destroy_session_result"]["status"] == "destroyed"
    assert result["run_output"] == result["run_input"]
    assert result["cleanup"]["exit_code"] == 0
