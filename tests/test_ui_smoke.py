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
    assert "Assistant" in window.windowTitle()
    assert window.stop_button.objectName() == "stop"
    window.chat.input.setText("List the Downloads folder")
    assert window.chat.input.text().startswith("List")


def test_approval_dialog_has_no_standing_permission(qtbot):
    preview = ApprovalPreview(
        step_id="s1",
        tool="move_to_recycle_bin",
        objective="Move to the Recycle Bin",
        risk=RiskLevel.high,
        impact="Only this file will be moved.",
        paths=[r"C:\Users\example\Downloads\a.txt"],
        reasons=["High risk"],
    )
    dialog = ApprovalDialog(preview)
    qtbot.addWidget(dialog)
    text = dialog.findChild(QPlainTextEdit).toPlainText()
    assert "will not be kept as a future permission" in text
    assert "a.txt" in text
    assert "always allow" not in text.lower()
