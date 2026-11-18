"""Shared structured records for plans, tools, and approvals."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class RiskLevel(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class StepStatus(StrEnum):
    pending = "pending"
    awaiting_approval = "awaiting_approval"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    warning = "warning"
    skipped = "skipped"
    cancelled = "cancelled"


class TaskStatus(StrEnum):
    running = "running"
    completed = "completed"
    completed_with_warnings = "completed_with_warnings"
    failed = "failed"
    needs_clarification = "needs_clarification"
    cancelled = "cancelled"


class PlanStep(BaseModel):
    id: str
    objective: str
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    risk: RiskLevel = RiskLevel.low
    requires_approval: bool = False
    expected_result: str = ""
    actual_result: str | None = None
    status: StepStatus = StepStatus.pending
    error: str | None = None
    attempts: int = 0
    approval_status: str = "not_required"


class Plan(BaseModel):
    intent: str
    assumptions: list[str] = Field(default_factory=list)
    steps: list[PlanStep] = Field(default_factory=list)
    clarification: str | None = None
    reactive: bool = False


class ToolResult(BaseModel):
    ok: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    error_code: str | None = None
    verified: bool = False
    verification_detail: str = ""
    message: str = ""


class Preflight(BaseModel):
    summary: str = ""
    paths: list[str] = Field(default_factory=list)
    will_overwrite: bool = False
    impact: str = ""


class RiskDecision(BaseModel):
    risk: RiskLevel
    requires_approval: bool
    reasons: list[str] = Field(default_factory=list)


class ApprovalPreview(BaseModel):
    """A one-time preview. Approving it does not authorize any later action."""

    token: str = Field(default_factory=lambda: uuid4().hex)
    step_id: str
    tool: str
    objective: str
    risk: RiskLevel
    impact: str
    paths: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class TaskReport(BaseModel):
    task_id: str
    status: TaskStatus
    report: str
    steps: list[dict[str, Any]] = Field(default_factory=list)
    clarification: str | None = None
    assumptions: list[str] = Field(default_factory=list)


ChatRole = Literal["system", "user", "assistant"]


class ChatMessage(BaseModel):
    role: ChatRole
    content: str
    image_paths: list[str] = Field(default_factory=list)
