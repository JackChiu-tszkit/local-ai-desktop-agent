"""Settings for providers, timeouts, and explicit cloud privacy switches."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from app.config.settings import AppSettings
from app.llm.cloud_provider import CloudProvider
from app.llm.ollama_provider import OllamaProvider
from app.storage.secrets import delete_api_key, load_api_key, store_api_key


class SettingsPanel(QDialog):
    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(560, 640)
        self._settings = settings
        self._result: AppSettings | None = None
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.provider = QComboBox()
        self.provider.addItem("本地 Ollama", "ollama")
        self.provider.addItem("云端（需手动开启）", "cloud")
        self.provider.setCurrentIndex(0 if settings.provider == "ollama" else 1)
        self.ollama_url = QLineEdit(settings.ollama_base_url)
        self.ollama_model = QLineEdit(settings.ollama_model)
        self.ollama_vision = QCheckBox("本地模型支持视觉，允许把本地截屏发给它")
        self.ollama_vision.setChecked(settings.ollama_vision)
        self.cloud_enabled = QCheckBox("开启云端推理")
        self.cloud_enabled.setChecked(settings.cloud_enabled)
        self.cloud_url = QLineEdit(settings.cloud_base_url)
        self.cloud_model = QLineEdit(settings.cloud_model)
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("留空则保持凭据管理器中的现有密钥")
        self.cloud_screenshots = QCheckBox("允许把截屏发送到云端")
        self.cloud_screenshots.setChecked(settings.cloud_allow_screenshots)
        self.cloud_files = QCheckBox("允许把文件内容发送到云端")
        self.cloud_files.setChecked(settings.cloud_allow_file_contents)
        self.cloud_paths = QCheckBox("允许把文件路径发送到云端")
        self.cloud_paths.setChecked(settings.cloud_allow_paths)
        self.cloud_vision = QCheckBox("云端模型支持视觉")
        self.cloud_vision.setChecked(settings.cloud_vision)
        self.task_timeout = QSpinBox()
        self.task_timeout.setRange(10, 3600)
        self.task_timeout.setValue(int(settings.task_timeout_seconds))
        self.step_timeout = QSpinBox()
        self.step_timeout.setRange(1, 600)
        self.step_timeout.setValue(int(settings.step_timeout_seconds))
        self.max_steps = QSpinBox()
        self.max_steps.setRange(1, 30)
        self.max_steps.setValue(settings.max_steps)
        form.addRow("推理来源", self.provider)
        form.addRow("Ollama 地址", self.ollama_url)
        form.addRow("Ollama 模型", self.ollama_model)
        form.addRow("", self.ollama_vision)
        form.addRow("", self.cloud_enabled)
        form.addRow("云端地址", self.cloud_url)
        form.addRow("云端模型", self.cloud_model)
        form.addRow("API 密钥", self.api_key)
        form.addRow("", self.cloud_screenshots)
        form.addRow("", self.cloud_files)
        form.addRow("", self.cloud_paths)
        form.addRow("", self.cloud_vision)
        form.addRow("任务超时（秒）", self.task_timeout)
        form.addRow("步骤超时（秒）", self.step_timeout)
        form.addRow("最大步骤数", self.max_steps)
        layout.addLayout(form)
        note = QLabel("云端默认关闭。开启后，只有你输入的指令会发送出去；文件内容、路径和截屏仍需各自单独勾选。密钥写入 Windows 凭据管理器，不写入数据库。")
        note.setWordWrap(True)
        note.setObjectName("subtle")
        layout.addWidget(note)
        try:
            self._key_stored = bool(load_api_key())
        except Exception:
            self._key_stored = False
        self.key_label = QLabel("凭据管理器中已有密钥。" if self._key_stored else "凭据管理器中还没有密钥。")
        layout.addWidget(self.key_label)
        row = QHBoxLayout()
        test = QPushButton("测试连接")
        test.setObjectName("secondary")
        test.clicked.connect(self._test_connection)
        clear = QPushButton("清除密钥")
        clear.setObjectName("secondary")
        clear.clicked.connect(self._clear_key)
        row.addWidget(test)
        row.addWidget(clear)
        row.addStretch(1)
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._ping: QThread | None = None

    def value(self) -> AppSettings | None:
        return self._result

    def _collect(self) -> AppSettings:
        data = self._settings.model_dump()
        data.update(
            {
                "provider": self.provider.currentData(),
                "ollama_base_url": self.ollama_url.text().strip(),
                "ollama_model": self.ollama_model.text().strip(),
                "ollama_vision": self.ollama_vision.isChecked(),
                "cloud_enabled": self.cloud_enabled.isChecked(),
                "cloud_base_url": self.cloud_url.text().strip(),
                "cloud_model": self.cloud_model.text().strip(),
                "cloud_allow_screenshots": self.cloud_screenshots.isChecked(),
                "cloud_allow_file_contents": self.cloud_files.isChecked(),
                "cloud_allow_paths": self.cloud_paths.isChecked(),
                "cloud_vision": self.cloud_vision.isChecked(),
                "task_timeout_seconds": self.task_timeout.value(),
                "step_timeout_seconds": self.step_timeout.value(),
                "max_steps": self.max_steps.value(),
            }
        )
        return AppSettings.model_validate(data)

    def _save(self) -> None:
        settings = self._collect()
        secret = self.api_key.text().strip()
        if secret:
            try:
                store_api_key(secret)
            except Exception as exc:
                QMessageBox.warning(self, "密钥没有保存", f"无法写入凭据管理器：{exc}")
                return
        try:
            settings.save()
        except Exception as exc:
            QMessageBox.warning(self, "设置没有保存", str(exc))
            return
        self._result = settings
        self.accept()

    def _clear_key(self) -> None:
        try:
            delete_api_key()
        except Exception as exc:
            QMessageBox.warning(self, "没有清除密钥", str(exc))
            return
        self.api_key.clear()
        self.key_label.setText("凭据管理器中还没有密钥。")

    def _test_connection(self) -> None:
        settings = self._collect()
        typed_key = self.api_key.text().strip()

        class Ping(QThread):
            done = Signal(bool, str)

            def run(self) -> None:
                try:
                    if settings.provider == "cloud":
                        provider = CloudProvider(settings, typed_key or load_api_key())
                    else:
                        provider = OllamaProvider(settings)
                    ok, message = provider.health()
                except Exception as exc:
                    ok, message = False, str(exc)
                self.done.emit(ok, message)

        self._ping = Ping(self)
        self._ping.done.connect(lambda ok, message: QMessageBox.information(self, "连接测试", message))
        self._ping.start()
