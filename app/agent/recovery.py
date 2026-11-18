"""Decide whether to advance, retry, replan, or stop. Retries are capped."""

from __future__ import annotations


def decide(
    *,
    status: str,
    error_code: str | None,
    attempts: int,
    revisions: int,
    max_retries: int,
    max_replans: int,
) -> str:
    if status in {"succeeded", "warning"}:
        return "advance"
    code = error_code or ""
    if code == "cancelled":
        return "stop"
    if code == "denied":
        return "stop"
    if code == "ambiguous":
        return "clarify"
    if code == "permission":
        return "fail"
    if code in {"timeout", "window_not_ready"} and attempts < max_retries:
        return "retry"
    if code in {"not_found", "verification_failed", "timeout", "window_not_ready"} and revisions < max_replans:
        return "replan"
    return "fail"
