"""Serializable agent state and the user-facing report."""

from __future__ import annotations

STATUS_LABELS = {
    "completed": "已完成",
    "completed_with_warnings": "已完成，但有窗口未确认",
    "failed": "未完成",
    "needs_clarification": "需要补充说明",
    "cancelled": "已停止",
    "running": "进行中",
}

STEP_LABELS = {
    "pending": "等待",
    "awaiting_approval": "等待确认",
    "running": "执行中",
    "succeeded": "已核对",
    "failed": "失败",
    "warning": "已执行但未确认窗口",
    "skipped": "跳过",
    "cancelled": "已停止",
}


def overall_status(steps: list[dict], forced: str | None = None) -> str:
    if forced in {"cancelled", "needs_clarification"}:
        return forced
    if forced == "completed":
        if any(str(step.get("status", "")) == "failed" for step in steps):
            return "completed_with_warnings"
        return "completed"
    statuses = [str(step.get("status", "")) for step in steps]
    if forced == "failed" or any(status == "failed" for status in statuses):
        return "failed"
    if any(status == "warning" for status in statuses):
        return "completed_with_warnings"
    if statuses and all(status == "succeeded" for status in statuses):
        return "completed"
    return forced or "failed"


def render_report(
    *,
    instruction: str,
    status: str,
    steps: list[dict],
    assumptions: list[str],
    clarification: str | None = None,
    error: str | None = None,
) -> str:
    lines = [f"任务状态：{STATUS_LABELS.get(status, status)}", ""]
    if clarification:
        lines.extend([clarification, ""])
    if status == "needs_clarification" and not steps:
        return clarification or "请把目标说得更具体。"
    if assumptions:
        lines.append("执行前的假设：")
        lines.extend(f"- {item}" for item in assumptions)
        lines.append("")
    if not steps:
        lines.append("没有执行任何操作。")
    else:
        lines.append("执行记录：")
        for index, step in enumerate(steps, start=1):
            label = STEP_LABELS.get(str(step.get("status")), str(step.get("status")))
            lines.append(f"{index}. [{label}] {step.get('objective', '')}")
            if step.get("actual_result"):
                lines.append(f"   结果：{step['actual_result']}")
            if step.get("error"):
                lines.append(f"   错误：{step['error']}")
    if error and error not in "\n".join(lines):
        lines.extend(["", error])
    lines.extend(["", f"原始指令：{instruction}"])
    return "\n".join(lines).strip()
