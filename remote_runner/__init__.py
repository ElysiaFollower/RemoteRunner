"""Remote Runner: transparent persistent local terminals for agents and humans."""

from remote_runner.bootstrap import BootstrapSession
from remote_runner.instance import InstanceManager
from remote_runner.session import ReadResult, SessionManager, TailResult
from remote_runner.state import StateStore
from remote_runner.tmux import TmuxTerminal

__version__ = "0.4.0"

__all__ = [
    "BootstrapSession",
    "InstanceManager",
    "ReadResult",
    "SessionManager",
    "StateStore",
    "TailResult",
    "TmuxTerminal",
]
