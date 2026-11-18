"""Serializable agent state and the user-facing report."""

from __future__ import annotations

STATUS_LABELS = {
    "completed": "Completed",
    "completed_with_warnings": "Completed, with an unconfirmed window",
    "failed": "Not completed",
    "needs_clarification": "Needs more detail",
    "cancelled": "Stopped",
    "running": "Running",
}

STEP_LABELS = {
    "pending": "Waiting",
    "awaiting_approval": "Waiting for confirmation",
    "running": "Running",
    "succeeded": "Verified",
    "failed": "Failed",
    "warning": "Ran, but the window was not confirmed",
    "skipped": "Skipped",
    "cancelled": "Stopped",
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
    lines = [f"Status: {STATUS_LABELS.get(status, status)}", ""]
    if clarification:
        lines.extend([clarification, ""])
    if status == "needs_clarification" and not steps:
        return clarification or "Please describe the goal more specifically."
    if assumptions:
        lines.append("Assumptions:")
        lines.extend(f"- {item}" for item in assumptions)
        lines.append("")
    if not steps:
        lines.append("No actions were run.")
    else:
        lines.append("Steps:")
        for index, step in enumerate(steps, start=1):
            label = STEP_LABELS.get(str(step.get("status")), str(step.get("status")))
            lines.append(f"{index}. [{label}] {step.get('objective', '')}")
            if step.get("actual_result"):
                lines.append(f"   Result: {step['actual_result']}")
            if step.get("error"):
                lines.append(f"   Error: {step['error']}")
    if error and error not in "\n".join(lines):
        lines.extend(["", error])
    lines.extend(["", f"Original instruction: {instruction}"])
    return "\n".join(lines).strip()
