import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QPlainTextEdit

from app.storage.models import ApprovalPreview, RiskLevel
from app.ui.approval_dialog import ApprovalDialog
from app.ui.main_window import MainWindow


def test_window_opens_without_running_a_task(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DATA_DIR", str(tmp_path))
    window = MainWindow()
    qtbot.addWidget(window)
    assert "助手" in window.windowTitle()
    assert window.stop_button.objectName() == "stop"
    window.chat.input.setText("列出下载文件夹")
    assert window.chat.input.text().startswith("列出")


def test_approval_dialog_has_no_standing_permission(qtbot):
    preview = ApprovalPreview(
        step_id="s1",
        tool="move_to_recycle_bin",
        objective="移动到回收站",
        risk=RiskLevel.high,
        impact="只移动这一个文件。",
        paths=[r"C:\Users\example\Downloads\a.txt"],
        reasons=["高风险"],
    )
    dialog = ApprovalDialog(preview)
    qtbot.addWidget(dialog)
    text = dialog.findChild(QPlainTextEdit).toPlainText()
    assert "不会保留为以后的权限" in text
    assert "a.txt" in text
    assert "始终" not in text
    assert "总是" not in text
