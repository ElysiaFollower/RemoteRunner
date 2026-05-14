"""Legacy compatibility wrapper for ``remote_runner.remote_terminal``."""

from remote_runner.remote_terminal import RemoteTerminalManager, get_remote_terminal_manager

__all__ = [
    "RemoteTerminalManager",
    "get_remote_terminal_manager",
]
