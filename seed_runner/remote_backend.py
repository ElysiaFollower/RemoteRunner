"""Legacy compatibility wrapper for ``remote_runner.remote_backend``."""

from remote_runner.remote_backend import (
    ParamikoRemoteBackend,
    RemoteCommandResult,
    get_remote_backend,
)

__all__ = [
    "ParamikoRemoteBackend",
    "RemoteCommandResult",
    "get_remote_backend",
]
