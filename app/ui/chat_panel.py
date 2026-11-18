"""Conversation pane."""

from __future__ import annotations

import html

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.examples import EXAMPLES


class ChatPanel(QWidget):
    submit_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.transcript = QTextBrowser()
        self.transcript.setOpenExternalLinks(False)
        layout.addWidget(self.transcript, 1)
        examples = QHBoxLayout()
        for example in EXAMPLES[:4]:
            button = QPushButton(example[:18] + "…")
            button.setObjectName("secondary")
            button.setToolTip(example)
            button.clicked.connect(lambda _checked=False, text=example: self.input.setText(text))
            examples.addWidget(button)
        layout.addLayout(examples)
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Describe the result you want")
        self.input.returnPressed.connect(self._emit)
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self._emit)
        row.addWidget(self.input, 1)
        row.addWidget(self.send_button)
        layout.addLayout(row)
        self.append_agent(
            "Describe the result. File search uses the filesystem. "
            "Deletion only moves items to the Recycle Bin, and each one needs its own confirmation."
        )

    def append_user(self, text: str) -> None:
        self._append("You", text)

    def append_agent(self, text: str) -> None:
        self._append("Assistant", text)

    def set_busy(self, busy: bool) -> None:
        self.input.setEnabled(not busy)
        self.send_button.setEnabled(not busy)

    def _emit(self) -> None:
        text = self.input.text().strip()
        if text:
            self.submit_requested.emit(text)
            self.input.clear()

    def _append(self, speaker: str, text: str) -> None:
        safe = html.escape(text).replace("\n", "<br>")
        self.transcript.append(f"<p><b>{speaker}</b><br>{safe}</p>")
