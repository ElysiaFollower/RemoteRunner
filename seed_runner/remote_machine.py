"""Legacy compatibility wrapper for ``remote_runner.remote_machine``."""

from remote_runner.remote_machine import (
    RemoteMachine,
    RemoteMachineManager,
    get_remote_machine_manager,
    redact_machine_record,
)

__all__ = [
    "RemoteMachine",
    "RemoteMachineManager",
    "get_remote_machine_manager",
    "redact_machine_record",
]
