"""Append-only audit records stored in the local database."""

from __future__ import annotations

from app.storage.database import Database


class AuditLog:
    def __init__(self, database: Database) -> None:
        self.database = database

    def record(
        self,
        *,
        task_id: str | None,
        action: str,
        risk: str,
        target: str,
        decision: str,
        detail: str,
    ) -> None:
        safe_detail = detail
        if action == "type_text":
            safe_detail = "Recorded a typing action. The text is not written to the audit log."
        self.database.add_audit(
            task_id=task_id,
            action=action,
            risk=risk,
            target=target,
            decision=decision,
            detail=safe_detail,
        )
