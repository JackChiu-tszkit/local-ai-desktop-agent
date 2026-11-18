"""Execute one planned step after policy, approval, and argument resolution."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.agent.desktop import is_unattended_desktop_tool
from app.agent.refs import resolve_arguments
from app.errors import AgentError, AmbiguousTargetError, CancellationError
from app.security.audit import AuditLog
from app.security.risk_classifier import classify
from app.storage.database import Database
from app.storage.models import ApprovalPreview, ToolResult
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry

_SECRET_ARGUMENT_TOOLS = {"type_text", "hotkey", "press_key", "create_text_file"}


class StepExecutor:
    def __init__(self, registry: ToolRegistry, approval, audit: AuditLog, database: Database) -> None:
        self.registry = registry
        self.approval = approval
        self.audit = audit
        self.database = database

    def run_step(
        self,
        *,
        task_id: str,
        position: int,
        step: dict[str, Any],
        results: dict[str, dict],
        ctx: ToolContext,
    ) -> ToolResult:
        step["status"] = "running"
        step["attempts"] = int(step.get("attempts", 0)) + 1
        self._checkpoint(task_id, position, step, None)
        try:
            resolved = resolve_arguments(step.get("arguments", {}), results)
            if not isinstance(resolved, dict):
                raise AgentError("工具参数无效")
            self._reject_secret_arguments(step["tool"], resolved)
            preflight = None
            try:
                preflight = self.registry.preflight(step["tool"], resolved, ctx)
            except ValidationError as exc:
                return self._finish(task_id, position, step, ToolResult(ok=False, error=str(exc), error_code="permission"))
            decision = classify(step["tool"], resolved, preflight)
            step["risk"] = decision.risk.value
            step["requires_approval"] = decision.requires_approval
            ctx.approved = False
            desktop = bool(step.get("desktop_control")) and is_unattended_desktop_tool(step["tool"])
            if decision.requires_approval and not desktop:
                step["status"] = "awaiting_approval"
                preview = ApprovalPreview(
                    step_id=step["id"],
                    tool=step["tool"],
                    objective=step["objective"],
                    risk=decision.risk,
                    impact=(preflight.impact if preflight and preflight.impact else "；".join(decision.reasons)),
                    paths=list(preflight.paths) if preflight else _collect_paths(resolved),
                    reasons=decision.reasons,
                )
                if step["tool"] == "type_text":
                    preview.impact = f"将向窗口“{resolved.get('window_title', '')}”输入以下文本：\n{resolved.get('text', '')}"
                approved = self.approval.request(preview)
                self.audit.record(
                    task_id=task_id,
                    action=step["tool"],
                    risk=decision.risk.value,
                    target="; ".join(preview.paths) or step["objective"],
                    decision="approved" if approved else "denied",
                    detail=preview.impact if step["tool"] != "type_text" else f"确认令牌 {preview.token}",
                )
                if not approved:
                    result = ToolResult(ok=False, error="已拒绝这次操作，没有进行更改", error_code="denied")
                    step["approval_status"] = "denied"
                    return self._finish(task_id, position, step, result)
                step["approval_status"] = "approved"
                ctx.approved = True
            elif desktop:
                step["approval_status"] = "desktop"
                ctx.approved = True
                self.audit.record(
                    task_id=task_id,
                    action=step["tool"],
                    risk=decision.risk.value,
                    target=step.get("objective", ""),
                    decision="desktop",
                    detail="桌面任务已开始，这一步不再单独确认",
                )
            else:
                step["approval_status"] = "not_required"
            step["status"] = "running"
            if step["tool"] == "click_named":
                ctx.step_deadline = ctx.task_deadline
            _model, result = self.registry.call(step["tool"], resolved, ctx)
            return self._finish(task_id, position, step, result)
        except AmbiguousTargetError as exc:
            result = ToolResult(ok=False, error=str(exc), error_code="ambiguous", data={"candidates": exc.candidates})
            return self._finish(task_id, position, step, result)
        except CancellationError as exc:
            result = ToolResult(ok=False, error=str(exc), error_code="cancelled")
            return self._finish(task_id, position, step, result)
        except TimeoutError as exc:
            result = ToolResult(ok=False, error=str(exc), error_code="timeout")
            return self._finish(task_id, position, step, result)
        except PermissionError as exc:
            result = ToolResult(ok=False, error=str(exc), error_code="permission")
            return self._finish(task_id, position, step, result)
        except AgentError as exc:
            code = "not_found" if "没有找到" in str(exc) else "permission"
            return self._finish(task_id, position, step, ToolResult(ok=False, error=str(exc), error_code=code))
        except Exception as exc:
            return self._finish(task_id, position, step, ToolResult(ok=False, error=str(exc), error_code="tool_error"))

    def _finish(self, task_id: str, position: int, step: dict, result: ToolResult) -> ToolResult:
        self._checkpoint(task_id, position, step, result.data if result.data else None)
        self.audit.record(
            task_id=task_id,
            action=step.get("tool", ""),
            risk=str(step.get("risk", "")),
            target=step.get("objective", ""),
            decision=result.error_code or ("ok" if result.ok else "error"),
            detail=result.message or result.error or "",
        )
        return result

    def _checkpoint(self, task_id: str, position: int, step: dict, result: dict | None) -> None:
        self.database.save_step(task_id, position, _jsonable_step(step), result)

    @staticmethod
    def _reject_secret_arguments(tool: str, arguments: dict) -> None:
        if tool not in _SECRET_ARGUMENT_TOOLS:
            return
        blob = json.dumps(arguments, ensure_ascii=False)
        from app.agent.planner import looks_like_secret_request

        if looks_like_secret_request(blob):
            raise PermissionError("已拒绝处理密码或密钥")


def _jsonable_step(step: dict) -> dict:
    item = dict(step)
    risk = item.get("risk")
    status = item.get("status")
    item["risk"] = getattr(risk, "value", risk)
    item["status"] = getattr(status, "value", status)
    return item


def _collect_paths(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, str) and (":\\" in value or value.startswith("\\\\")):
        found.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            found.extend(_collect_paths(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_collect_paths(item))
    return found
