"""Current steps and saved task history."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QTabWidget, QVBoxLayout, QWidget

from app.agent.state import STEP_LABELS


class TaskPanel(QWidget):
    history_selected = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.steps = QListWidget()
        self.history = QListWidget()
        self.tabs.addTab(self.steps, "Current steps")
        self.tabs.addTab(self.history, "History")
        layout.addWidget(self.tabs)
        self.history.itemClicked.connect(self._clicked)
        self._rows: dict[str, QListWidgetItem] = {}

    def clear_steps(self) -> None:
        self.steps.clear()
        self._rows.clear()

    def upsert_step(self, step: dict) -> None:
        status = STEP_LABELS.get(str(step.get("status")), str(step.get("status")))
        text = f"[{status}] {step.get('objective', '')}"
        if step.get("actual_result"):
            text += f"\n{step['actual_result']}"
        if step.get("error"):
            text += f"\n{step['error']}"
        item = self._rows.get(step.get("id", ""))
        if item is None:
            item = QListWidgetItem(text)
            self.steps.addItem(item)
            self._rows[step.get("id", "")] = item
        else:
            item.setText(text)

    def set_history(self, tasks: list[dict]) -> None:
        self.history.clear()
        for task in tasks:
            label = f"{task['created_at']}  {task['status']}\n{task['instruction'][:80]}"
            item = QListWidgetItem(label)
            item.setData(256, task["id"])
            self.history.addItem(item)

    def _clicked(self, item: QListWidgetItem) -> None:
        task_id = item.data(256)
        if task_id:
            self.history_selected.emit(str(task_id))
