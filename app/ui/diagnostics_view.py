from __future__ import annotations

import json

from .qt_compat import PYSIDE6_AVAILABLE, require_pyside6

# Diagnostics surfaces: FFmpeg, CUDA, Components, Jobs, and Export diagnostics.
DIAGNOSTIC_SECTIONS = ("FFmpeg", "CUDA", "Components", "Jobs")

if PYSIDE6_AVAILABLE:
    from PySide6.QtWidgets import QLabel, QPushButton, QPlainTextEdit, QVBoxLayout, QWidget

    class DiagnosticsView(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            layout = QVBoxLayout(self)
            layout.addWidget(QLabel("Diagnostics — FFmpeg / CUDA / Components / Jobs"))
            self.summary = QPlainTextEdit()
            self.summary.setReadOnly(True)
            layout.addWidget(self.summary, 1)
            self.export_button = QPushButton("Export diagnostics")
            layout.addWidget(self.export_button)

        def set_report(self, report: dict[str, object]) -> None:
            self.summary.setPlainText(json.dumps(report, ensure_ascii=False, indent=2))
else:
    class DiagnosticsView:
        def __init__(self, *args, **kwargs):
            require_pyside6()
