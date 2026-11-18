"""One-time approval. There is intentionally no “always allow” choice."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
)

from app.storage.models import ApprovalPreview


class ApprovalDialog(QDialog):
    def __init__(self, preview: ApprovalPreview, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Confirm this action")
        self.resize(640, 460)
        layout = QVBoxLayout(self)
        title = QLabel(preview.objective)
        title.setObjectName("title")
        title.setWordWrap(True)
        layout.addWidget(title)
        risk = QLabel(f"Risk: {preview.risk.value}    Confirmation: {preview.token[:8]}")
        risk.setObjectName("subtle")
        layout.addWidget(risk)
        detail = QPlainTextEdit()
        detail.setReadOnly(True)
        body = [preview.impact or "Confirm whether to run this action once.", ""]
        if preview.paths:
            body.append("Target paths:")
            body.extend(preview.paths)
        if preview.reasons:
            body.extend(["", "Reasons:"])
            body.extend(f"- {reason}" for reason in preview.reasons)
        body.extend(["", "Allowing this applies only to the action listed above. It will not be kept as a future permission."])
        detail.setPlainText("\n".join(body))
        layout.addWidget(detail)
        buttons = QDialogButtonBox()
        allow = buttons.addButton("Allow once", QDialogButtonBox.ButtonRole.AcceptRole)
        deny = buttons.addButton("Deny", QDialogButtonBox.ButtonRole.RejectRole)
        allow.setDefault(False)
        deny.setObjectName("stop")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(buttons)
        layout.addLayout(row)
