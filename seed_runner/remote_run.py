"""Legacy compatibility wrapper for ``remote_runner.remote_run``."""

from remote_runner.remote_run import RemoteRunManager, get_remote_run_manager

__all__ = [
    "RemoteRunManager",
    "get_remote_run_manager",
]
