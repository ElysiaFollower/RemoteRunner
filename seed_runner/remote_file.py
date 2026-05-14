"""Legacy compatibility wrapper for ``remote_runner.remote_file``."""

from remote_runner.remote_file import RemoteFileManager, get_remote_file_manager

__all__ = [
    "RemoteFileManager",
    "get_remote_file_manager",
]
