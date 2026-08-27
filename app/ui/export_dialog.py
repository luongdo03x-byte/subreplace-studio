from __future__ import annotations

from .qt_compat import PYSIDE6_AVAILABLE, require_pyside6

if PYSIDE6_AVAILABLE:
    from PySide6.QtWidgets import (
        QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
        QLineEdit, QPushButton, QWidget,
    )

    class ExportDialog(QDialog):
        def __init__(self, parent=None, *, default_output: str = ""):
            super().__init__(parent)
            self.setWindowTitle("Export")
            layout = QFormLayout(self)
            self.output_path = QLineEdit(default_output)
            browse = QPushButton("Browse…")
            browse.clicked.connect(self._browse)
            row = QHBoxLayout(); row.addWidget(self.output_path, 1); row.addWidget(browse)
            holder = QWidget(); holder.setLayout(row)
            self.export_subtitle = QCheckBox("Also export SRT (may duplicate burned-in subtitles in players)")
            self.export_clean = QCheckBox("Also export lossless clean video")
            self.export_project = QCheckBox("Also export portable .subreplace project")
            self.export_project.setChecked(True)
            layout.addRow("Output folder", holder)
            layout.addRow(self.export_subtitle)
            layout.addRow(self.export_clean)
            layout.addRow(self.export_project)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            layout.addRow(buttons)

        def _browse(self) -> None:
            selected = QFileDialog.getExistingDirectory(self, "Export folder", self.output_path.text())
            if selected:
                self.output_path.setText(selected)
else:
    class ExportDialog:
        def __init__(self, *args, **kwargs):
            require_pyside6()
