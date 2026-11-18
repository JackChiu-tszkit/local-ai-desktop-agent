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
        self.setWindowTitle("确认这一次操作")
        self.resize(640, 460)
        layout = QVBoxLayout(self)
        title = QLabel(preview.objective)
        title.setObjectName("title")
        title.setWordWrap(True)
        layout.addWidget(title)
        risk = QLabel(f"风险：{preview.risk.value}    确认编号：{preview.token[:8]}")
        risk.setObjectName("subtle")
        layout.addWidget(risk)
        detail = QPlainTextEdit()
        detail.setReadOnly(True)
        body = [preview.impact or "请确认是否执行这一次操作。", ""]
        if preview.paths:
            body.append("目标路径：")
            body.extend(preview.paths)
        if preview.reasons:
            body.extend(["", "原因："])
            body.extend(f"- {reason}" for reason in preview.reasons)
        body.extend(["", "允许只作用于上面列出的这一次操作，不会保留为以后的权限。"])
        detail.setPlainText("\n".join(body))
        layout.addWidget(detail)
        buttons = QDialogButtonBox()
        allow = buttons.addButton("允许这一次", QDialogButtonBox.ButtonRole.AcceptRole)
        deny = buttons.addButton("拒绝", QDialogButtonBox.ButtonRole.RejectRole)
        allow.setDefault(False)
        deny.setObjectName("stop")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(buttons)
        layout.addLayout(row)
