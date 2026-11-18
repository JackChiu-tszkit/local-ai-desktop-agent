"""One-shot approvals. A decision never becomes a standing permission."""

from __future__ import annotations

from collections.abc import Callable

from app.storage.models import ApprovalPreview


class ApprovalManager:
    def __init__(self, callback: Callable[[ApprovalPreview], bool]) -> None:
        self._callback = callback
        self.history: list[tuple[str, str, bool]] = []

    def request(self, preview: ApprovalPreview) -> bool:
        decision = bool(self._callback(preview))
        self.history.append((preview.token, preview.tool, decision))
        return decision


class ScriptedApproval:
    def __init__(self, decision: bool = True, deny_tools: set[str] | None = None) -> None:
        self.decision = decision
        self.deny_tools = deny_tools or set()
        self.previews: list[ApprovalPreview] = []

    def request(self, preview: ApprovalPreview) -> bool:
        self.previews.append(preview)
        if preview.tool in self.deny_tools:
            return False
        return self.decision
