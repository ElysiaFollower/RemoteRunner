"""File transfer facade for the target ``remote_runner`` package."""

from seed_runner.remote_file import RemoteFileManager, get_remote_file_manager

__all__ = [
    "RemoteFileManager",
    "get_remote_file_manager",
]
