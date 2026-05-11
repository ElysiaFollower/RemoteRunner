"""Run orchestration facade for the target ``remote_runner`` package."""

from seed_runner.remote_run import RemoteRunManager, get_remote_run_manager

__all__ = [
    "RemoteRunManager",
    "get_remote_run_manager",
]
