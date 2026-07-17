"""Stable error types for the Remote Runner command interface."""

from typing import Any, Dict, Optional


class RemoteRunnerError(Exception):
    """An expected tool failure with a stable machine-readable code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        context: Optional[Dict[str, Any]] = None,
        exit_code: int = 1,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.context = dict(context or {})
        self.exit_code = exit_code

    def payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "error": {
                "code": self.code,
                "message": self.message,
            }
        }
        payload.update(self.context)
        return payload


class UsageError(RemoteRunnerError):
    def __init__(self, message: str) -> None:
        super().__init__("invalid_usage", message, exit_code=2)


class StateError(RemoteRunnerError):
    pass


class TmuxError(RemoteRunnerError):
    pass
