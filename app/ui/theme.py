APP_STYLE = """
QMainWindow, QDialog, QWidget { background: #f3f3f3; color: #1f1f1f; }
QTextBrowser, QPlainTextEdit, QTreeWidget, QListWidget {
    background: #ffffff;
    border: 1px solid #e2e2e2;
    border-radius: 8px;
    padding: 8px;
}
QLineEdit, QComboBox, QSpinBox {
    background: #ffffff;
    border: 1px solid #d0d0d0;
    border-radius: 6px;
    padding: 6px 8px;
    min-height: 28px;
}
QPushButton {
    background: #0f6cbd;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 14px;
}
QPushButton:disabled { background: #b9c7d6; }
QPushButton#secondary {
    background: #ffffff;
    color: #1f1f1f;
    border: 1px solid #d0d0d0;
}
QPushButton#stop { background: #c42b1c; }
QLabel#title { font-size: 20px; font-weight: 600; }
QLabel#subtle { color: #5d5d5d; }
QStatusBar { background: #ffffff; }
QSplitter::handle { background: #e6e6e6; }
"""
