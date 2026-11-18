"""Errors that change control flow in the agent loop."""


class AgentError(Exception):
    """Base error for expected agent failures."""


class CancellationError(AgentError):
    """The user pressed Stop or the task was cancelled."""


class AmbiguousTargetError(AgentError):
    """More than one file matches a singular action."""

    def __init__(self, message: str, candidates: list[str]) -> None:
        super().__init__(message)
        self.candidates = candidates


class ApprovalDeniedError(AgentError):
    """The user rejected one specific action preview."""
