"""SQLite storage for tasks, checkpoints, preferences, and audit records."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    instruction TEXT NOT NULL,
                    status TEXT NOT NULL,
                    provider TEXT,
                    report TEXT,
                    assumptions_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS steps (
                    task_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    objective TEXT,
                    tool TEXT,
                    arguments_json TEXT,
                    risk TEXT,
                    requires_approval INTEGER,
                    approval_status TEXT,
                    expected_result TEXT,
                    actual_result TEXT,
                    status TEXT,
                    error TEXT,
                    result_json TEXT,
                    attempts INTEGER DEFAULT 0,
                    PRIMARY KEY (task_id, step_id)
                );
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    task_id TEXT,
                    action TEXT NOT NULL,
                    risk TEXT,
                    target TEXT,
                    decision TEXT,
                    detail TEXT
                );
                CREATE TABLE IF NOT EXISTS preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            self._conn.commit()

    def create_task(self, task_id: str, instruction: str, provider: str, assumptions: list[str]) -> None:
        now = utc_now()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO tasks (id, instruction, status, provider, report, assumptions_json, created_at, updated_at)
                VALUES (?, ?, 'running', ?, '', ?, ?, ?)
                """,
                (task_id, instruction, provider, json.dumps(assumptions, ensure_ascii=False), now, now),
            )
            self._conn.commit()

    def update_task(
        self,
        task_id: str,
        status: str,
        report: str | None = None,
        assumptions: list[str] | None = None,
    ) -> None:
        with self._lock:
            row = self._conn.execute("SELECT report, assumptions_json FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                return
            next_report = row["report"] if report is None else report
            next_assumptions = row["assumptions_json"] if assumptions is None else json.dumps(assumptions, ensure_ascii=False)
            self._conn.execute(
                "UPDATE tasks SET status = ?, report = ?, assumptions_json = ?, updated_at = ? WHERE id = ?",
                (status, next_report, next_assumptions, utc_now(), task_id),
            )
            self._conn.commit()

    def save_step(self, task_id: str, position: int, step: dict[str, Any], result: dict[str, Any] | None) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO steps (
                    task_id, step_id, position, objective, tool, arguments_json, risk,
                    requires_approval, approval_status, expected_result, actual_result,
                    status, error, result_json, attempts
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id, step_id) DO UPDATE SET
                    position = excluded.position,
                    objective = excluded.objective,
                    tool = excluded.tool,
                    arguments_json = excluded.arguments_json,
                    risk = excluded.risk,
                    requires_approval = excluded.requires_approval,
                    approval_status = excluded.approval_status,
                    expected_result = excluded.expected_result,
                    actual_result = excluded.actual_result,
                    status = excluded.status,
                    error = excluded.error,
                    result_json = excluded.result_json,
                    attempts = excluded.attempts
                """,
                (
                    task_id,
                    step["id"],
                    position,
                    step.get("objective", ""),
                    step.get("tool", ""),
                    json.dumps(step.get("arguments", {}), ensure_ascii=False),
                    str(step.get("risk", "")),
                    1 if step.get("requires_approval") else 0,
                    step.get("approval_status", ""),
                    step.get("expected_result", ""),
                    step.get("actual_result"),
                    str(step.get("status", "")),
                    step.get("error"),
                    json.dumps(result, ensure_ascii=False) if result is not None else None,
                    int(step.get("attempts", 0)),
                ),
            )
            self._conn.commit()

    def add_audit(
        self,
        *,
        task_id: str | None,
        action: str,
        risk: str,
        target: str,
        decision: str,
        detail: str,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO audit (timestamp, task_id, action, risk, target, decision, detail)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (utc_now(), task_id, action, risk, target[:2000], decision, detail[:2000]),
            )
            self._conn.commit()

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def list_tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_steps(self, task_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM steps WHERE task_id = ?", (task_id,))
            self._conn.commit()

    def list_steps(self, task_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM steps WHERE task_id = ? ORDER BY position ASC",
                (task_id,),
            ).fetchall()
        steps: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["arguments"] = json.loads(item.pop("arguments_json") or "{}")
            raw_result = item.pop("result_json")
            item["result"] = json.loads(raw_result) if raw_result else None
            item["requires_approval"] = bool(item["requires_approval"])
            item["id"] = item.pop("step_id")
            steps.append(item)
        return steps

    def list_audit(self, task_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            if task_id is None:
                rows = self._conn.execute(
                    "SELECT * FROM audit ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM audit WHERE task_id = ? ORDER BY id DESC LIMIT ?",
                    (task_id, limit),
                ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
