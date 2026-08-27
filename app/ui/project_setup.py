from __future__ import annotations

from pathlib import Path

from app.core.credentials import CredentialStore

from .qt_compat import PYSIDE6_AVAILABLE, require_pyside6

if PYSIDE6_AVAILABLE:
    from PySide6.QtWidgets import (
        QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
        QLineEdit, QPushButton, QWidget,
    )

    class ProjectSetupView(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            layout = QFormLayout(self)
            help_text = QLabel("Chỉ cần chọn video, nơi lưu và nhập API key dịch. Các mục kỹ thuật đã được đặt sẵn cho máy này.")
            help_text.setWordWrap(True)
            layout.addRow(help_text)

            self.project_name = QLineEdit()
            self.project_name.setPlaceholderText("My translated video")
            layout.addRow("Tên dự án", self.project_name)

            self.source_path = QLineEdit()
            source_button = QPushButton("Browse…")
            source_button.clicked.connect(self._browse_source)
            source_row = QHBoxLayout(); source_row.addWidget(self.source_path, 1); source_row.addWidget(source_button)
            layout.addRow("Video cần dịch", source_row)

            self.project_root = QLineEdit()
            self.project_root.setText(str(Path.home() / "Videos"))
            project_button = QPushButton("Browse…")
            project_button.clicked.connect(self._browse_project_root)
            project_row = QHBoxLayout(); project_row.addWidget(self.project_root, 1); project_row.addWidget(project_button)
            layout.addRow("Thư mục video đã dịch", project_row)

            self.target_language = QComboBox()
            self.target_language.addItem("Vietnamese", "vi")
            self.target_language.addItem("English", "en")
            layout.addRow("Ngôn ngữ đích", self.target_language)

            self.translation_provider = QComboBox()
            for label, value in (("OpenAI", "openai"), ("Gemini", "gemini"), ("Custom API", "custom"), ("Local command", "local")):
                self.translation_provider.addItem(label, value)
            layout.addRow("Dịch bằng", self.translation_provider)

            self.translation_model = QLineEdit()
            self.translation_model.setPlaceholderText("Optional provider model")
            layout.addRow("Model dịch", self.translation_model)

            self.endpoint = QLineEdit()
            self.endpoint.setPlaceholderText("Custom API endpoint")
            layout.addRow("Custom endpoint", self.endpoint)

            self.api_key = QLineEdit()
            self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
            self.api_key.setPlaceholderText("Nhập API key OpenAI hoặc Gemini")
            layout.addRow("API key", self.api_key)
            self.remember_api_key = QCheckBox("Ghi nhớ API key an toàn trên máy này")
            self.remember_api_key.setChecked(True)
            layout.addRow(self.remember_api_key)
            self._credentials = CredentialStore()
            self.translation_provider.currentIndexChanged.connect(self._load_api_key)
            self._load_api_key()

            self.local_command = QLineEdit()
            self.local_command.setPlaceholderText("translator --json")
            layout.addRow("Local command", self.local_command)

            self.temporal_provider = QComboBox()
            for label, value in (("Classical only", "classical"), ("ProPainter", "propainter"), ("E2FGVI", "e2fgvi")):
                self.temporal_provider.addItem(label, value)
            layout.addRow("Background reconstruction", self.temporal_provider)

            self.temporal_repo_dir = QLineEdit()
            repo_button = QPushButton("Browse…")
            repo_button.clicked.connect(self._browse_temporal_repo)
            repo_row = QHBoxLayout(); repo_row.addWidget(self.temporal_repo_dir, 1); repo_row.addWidget(repo_button)
            self._repo_row = repo_row
            layout.addRow("AI plugin folder", repo_row)

            self.temporal_checkpoint = QLineEdit()
            checkpoint_button = QPushButton("Browse…")
            checkpoint_button.clicked.connect(self._browse_checkpoint)
            checkpoint_row = QHBoxLayout(); checkpoint_row.addWidget(self.temporal_checkpoint, 1); checkpoint_row.addWidget(checkpoint_button)
            self._checkpoint_row = checkpoint_row
            layout.addRow("E2FGVI checkpoint", checkpoint_row)

            self.fp16 = QCheckBox("Use FP16 when provider supports it")
            self.fp16.setChecked(False)
            layout.addRow(self.fp16)

            self.advanced = QCheckBox("Hiện cài đặt nâng cao")
            self.advanced.toggled.connect(self._set_advanced_visible)
            layout.addRow(self.advanced)

            self.process_button = QPushButton("Bắt đầu dịch video")
            layout.addRow(self.process_button)
            self._layout = layout
            self._set_advanced_visible(False)

        def _set_advanced_visible(self, visible: bool) -> None:
            for widget in (
                self.project_name, self.translation_model, self.endpoint, self.local_command,
                self.temporal_provider, self._repo_row, self._checkpoint_row, self.fp16,
            ):
                self._layout.setRowVisible(widget, visible)

        def _load_api_key(self) -> None:
            provider = str(self.translation_provider.currentData())
            self.api_key.setText(self._credentials.load(provider))

        def save_api_key(self) -> bool:
            provider = str(self.translation_provider.currentData())
            value = self.api_key.text().strip()
            if not self.remember_api_key.isChecked():
                self._credentials.delete(provider)
                return True
            return not value or self._credentials.save(provider, value)

        def _browse_source(self) -> None:
            path, _ = QFileDialog.getOpenFileName(self, "Select source video", "", "Video (*.mp4 *.mkv *.mov *.avi);;All files (*)")
            if path:
                self.source_path.setText(path)
                if not self.project_name.text().strip():
                    self.project_name.setText(Path(path).stem)

        def _browse_project_root(self) -> None:
            path = QFileDialog.getExistingDirectory(self, "Select project folder")
            if path:
                self.project_root.setText(path)

        def _browse_temporal_repo(self) -> None:
            path = QFileDialog.getExistingDirectory(self, "Select installed temporal AI repository")
            if path:
                self.temporal_repo_dir.setText(path)

        def _browse_checkpoint(self) -> None:
            path, _ = QFileDialog.getOpenFileName(self, "Select E2FGVI checkpoint", "", "Model weights (*.pth *.pt);;All files (*)")
            if path:
                self.temporal_checkpoint.setText(path)
else:
    class ProjectSetupView:
        def __init__(self, *args, **kwargs):
            require_pyside6()
