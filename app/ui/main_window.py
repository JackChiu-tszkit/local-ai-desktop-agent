"""Main desktop window."""

from __future__ import annotations

import logging
import threading

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.config.settings import AppSettings
from app.storage.database import Database
from app.ui.approval_dialog import ApprovalDialog
from app.ui.chat_panel import ChatPanel
from app.ui.settings_panel import SettingsPanel
from app.ui.task_panel import TaskPanel
from app.ui.theme import APP_STYLE
from app.ui.worker import AgentWorker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("本地桌面助手")
        self.resize(1180, 760)
        self.settings = AppSettings.load()
        data_dir = self.settings.resolved_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=data_dir / "agent.log",
            level=logging.INFO,
            encoding="utf-8",
            format="%(asctime)s %(levelname)s %(message)s",
        )
        self.database = Database(data_dir / "agent.db")
        self.cancel_event = threading.Event()
        self.worker: AgentWorker | None = None
        self.setStyleSheet(APP_STYLE)
        self._build()
        self._refresh_history()
        self._refresh_status()

    def _build(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("本地桌面助手")
        title.setObjectName("title")
        subtitle = QLabel("本地优先。高风险操作每次单独确认，停止按钮会中断后续步骤。")
        subtitle.setObjectName("subtle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        self.stop_button = QPushButton("停止")
        self.stop_button.setObjectName("stop")
        self.stop_button.clicked.connect(self.stop_task)
        settings_button = QPushButton("设置")
        settings_button.setObjectName("secondary")
        settings_button.clicked.connect(self.open_settings)
        header.addWidget(settings_button)
        header.addWidget(self.stop_button)
        layout.addLayout(header)
        splitter = QSplitter()
        self.chat = ChatPanel()
        self.tasks = TaskPanel()
        self.chat.submit_requested.connect(self.start_task)
        self.tasks.history_selected.connect(self.show_history)
        splitter.addWidget(self.chat)
        splitter.addWidget(self.tasks)
        splitter.setSizes([720, 420])
        layout.addWidget(splitter, 1)
        self.statusBar().showMessage(self._status_text())
        resume_action = QAction("继续未完成任务", self)
        resume_action.triggered.connect(self.resume_selected)
        self.menuBar().addAction(resume_action)

    def start_task(self, instruction: str) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        self.cancel_event.clear()
        self.chat.append_user(instruction)
        self.tasks.clear_steps()
        self.chat.set_busy(True)
        self._start_worker(instruction, None)

    def resume_selected(self) -> None:
        item = self.tasks.history.currentItem()
        if item is None:
            QMessageBox.information(self, "没有选择任务", "先在历史里选一条任务。")
            return
        task_id = str(item.data(256))
        self.cancel_event.clear()
        self.tasks.clear_steps()
        self.chat.set_busy(True)
        self._start_worker("", task_id)

    def _start_worker(self, instruction: str, task_id: str | None) -> None:
        self.worker = AgentWorker(instruction, self.settings, self.database, self.cancel_event, task_id)
        self.worker.step_changed.connect(self.tasks.upsert_step)
        self.worker.approval_needed.connect(self._approve)
        self.worker.finished_ok.connect(self._finished)
        self.worker.failed.connect(self._failed)
        self.worker.start()

    def stop_task(self) -> None:
        self.cancel_event.set()
        if self.worker is not None:
            self.worker.submit(False)
        self.statusBar().showMessage("正在停止")

    def open_settings(self) -> None:
        dialog = SettingsPanel(self.settings, self)
        if dialog.exec() and dialog.value() is not None:
            self.settings = dialog.value()
            self._refresh_status()

    def show_history(self, task_id: str) -> None:
        task = self.database.get_task(task_id)
        if task and task.get("report"):
            self.chat.append_agent(task["report"])

    def _approve(self, preview) -> None:
        dialog = ApprovalDialog(preview, self)
        approved = dialog.exec() == ApprovalDialog.DialogCode.Accepted
        if self.worker is not None:
            self.worker.submit(approved)

    def _finished(self, report) -> None:
        self.chat.append_agent(report.report)
        self.chat.set_busy(False)
        self._refresh_history()
        self._refresh_status()

    def _failed(self, message: str) -> None:
        self.chat.append_agent(f"任务没有完成：{message}")
        self.chat.set_busy(False)
        self._refresh_status()

    def _refresh_history(self) -> None:
        self.tasks.set_history(self.database.list_tasks())

    def _refresh_status(self) -> None:
        self.statusBar().showMessage(self._status_text())

    def _status_text(self) -> str:
        if self.settings.provider == "cloud":
            provider = "云端已开启" if self.settings.cloud_enabled else "云端未开启，只会使用本地规则"
        else:
            provider = f"Ollama · {self.settings.ollama_model}"
        return f"{provider}    超时 {int(self.settings.task_timeout_seconds)} 秒    允许目录：下载、文档、桌面、图片"
