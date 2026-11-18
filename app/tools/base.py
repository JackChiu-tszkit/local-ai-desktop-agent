"""Tool context and registration types."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from app.config.settings import AppSettings
from app.errors import CancellationError
from app.security.permissions import PathGuard
from app.storage.models import Preflight, RiskLevel, ToolResult


@dataclass
class ToolContext:
    guard: PathGuard
    folders: dict[str, Path]
    platform: object
    cancel_event: object
    task_deadline: float
    step_deadline: float
    settings: AppSettings
    provider: object | None = None
    approved: bool = False
    max_results: int = 200
    max_hash_bytes: int = 200 * 1024 * 1024
    screenshot_dir: Path | None = None
    task_id: str = ""

    def check_time(self) -> None:
        now = time.monotonic()
        if getattr(self.cancel_event, "is_set", lambda: False)():
            raise CancellationError("The task was stopped")
        if now > self.task_deadline:
            raise TimeoutError("The task timed out")
        if now > self.step_deadline:
            raise TimeoutError("The step timed out")


@dataclass
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[BaseModel, ToolContext], ToolResult]
    risk: RiskLevel
    preflight: Callable[[BaseModel, ToolContext], Preflight] | None = None
    requires_granted_flag: bool = False
    parameters: dict = field(default_factory=dict)
