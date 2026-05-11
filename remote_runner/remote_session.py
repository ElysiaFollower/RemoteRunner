"""Session facade for the target ``remote_runner`` package."""

from seed_runner.remote_session import RemoteSessionManager, get_remote_session_manager

__all__ = [
    "RemoteSessionManager",
    "get_remote_session_manager",
]
