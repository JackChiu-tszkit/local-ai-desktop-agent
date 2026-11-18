"""Runs one task off the UI thread and blocks only itself while waiting for approval."""

from __future__ import annotations

import threading

from PySide6.QtCore import QThread, Signal

from app.config.settings import AppSettings
from app.security.approval_manager import ApprovalManager
from app.storage.database import Database
from app.storage.models import ApprovalPreview


class AgentWorker(QThread):
    step_changed = Signal(dict)
    approval_needed = Signal(object)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        instruction: str,
        settings: AppSettings,
        database: Database,
        cancel_event: threading.Event,
        task_id: str | None = None,
    ) -> None:
        super().__init__()
        self.instruction = instruction
        self.settings = settings
        self.database = database
        self.cancel_event = cancel_event
        self.task_id = task_id
        self._decision = False
        self._decision_event = threading.Event()

    def submit(self, approved: bool) -> None:
        self._decision = approved
        self._decision_event.set()

    def _approve(self, preview: ApprovalPreview) -> bool:
        if self.cancel_event.is_set():
            return False
        self._decision_event.clear()
        self.approval_needed.emit(preview)
        while not self._decision_event.wait(0.2):
            if self.cancel_event.is_set():
                return False
        return self._decision

    def run(self) -> None:
        try:
            from app.runtime import build_agent

            agent = build_agent(
                settings=self.settings,
                approval=ApprovalManager(self._approve),
                database=self.database,
                cancel_event=self.cancel_event,
            )
            agent.on_step = lambda step: self.step_changed.emit(step)
            report = agent.resume(self.task_id) if self.task_id else agent.run(self.instruction)
            self.finished_ok.emit(report)
        except Exception as exc:
            self.failed.emit(str(exc))
