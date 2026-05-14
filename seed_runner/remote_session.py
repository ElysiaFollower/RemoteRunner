"""Legacy compatibility wrapper for ``remote_runner.remote_session``."""

from remote_runner.remote_session import RemoteSessionManager, get_remote_session_manager

__all__ = [
    "RemoteSessionManager",
    "get_remote_session_manager",
]
