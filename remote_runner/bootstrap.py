"""The public hook object used by per-instance bootstrap files."""

from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from remote_runner.session import ReadResult, SessionManager, TailResult


class BootstrapSession:
    """Expose normal terminal operations while one bootstrap owns the writer lock."""

    def __init__(self, manager: "SessionManager", session_id: str) -> None:
        self._manager = manager
        self.session_id = session_id

    @property
    def session_name(self) -> str:
        return str(self._manager._load_session(self.session_id)["session_name"])

    def send(self, line: str) -> Dict[str, Any]:
        return self._manager._send_locked(self.session_id, line)

    def key(self, key: str) -> Dict[str, Any]:
        return self._manager._key_locked(self.session_id, key)

    def read(self, from_cursor: int = 0, max_bytes: int = 65536) -> "ReadResult":
        return self._manager.read(self.session_id, from_cursor=from_cursor, max_bytes=max_bytes)

    def tail(self, max_bytes: int = 8192) -> "TailResult":
        return self._manager.tail(self.session_id, max_bytes=max_bytes)

    def show(self) -> Dict[str, Any]:
        return self._manager.show(self.session_id)
