from __future__ import annotations

from pathlib import Path

from .qt_compat import PYSIDE6_AVAILABLE, require_pyside6

if PYSIDE6_AVAILABLE:
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtWidgets import (
        QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
        QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
    )

    from app.application.library_service import LibraryService


    class SeriesLibraryView(QWidget):
        library_changed = Signal()

        def __init__(self, service: LibraryService, parent=None):
            super().__init__(parent)
            self.service = service
            root = QVBoxLayout(self)
            intro = QLabel(
                "SubReplace Next lưu Series/Episode trong database riêng. "
                "Số tập được lấy từ filename, không phụ thuộc thứ tự chọn file."
            )
            intro.setWordWrap(True)
            root.addWidget(intro)
            form = QFormLayout()
            self.name = QLineEdit(); self.name.setPlaceholderText("Tên series")
            self.base_title = QLineEdit(); self.base_title.setPlaceholderText("Base title dùng cho mọi tập")
            self.source_folder = QLineEdit()
            source_button = QPushButton("Chọn thư mục…"); source_button.clicked.connect(self._browse_source)
            source_row = QHBoxLayout(); source_row.addWidget(self.source_folder, 1); source_row.addWidget(source_button)
            self.output_folder = QLineEdit(str(Path.home() / "Videos" / "SubReplace Next"))
            output_button = QPushButton("Chọn nơi lưu…"); output_button.clicked.connect(self._browse_output)
            output_row = QHBoxLayout(); output_row.addWidget(self.output_folder, 1); output_row.addWidget(output_button)
            self.language = QComboBox(); self.language.addItem("Vietnamese", "vi"); self.language.addItem("English", "en")
            self.import_as_final = QCheckBox("Video trong Source folder đã là Final MP4 hoàn chỉnh")
            self.import_as_final.setChecked(True)
            form.addRow("Tên series", self.name); form.addRow("Base title", self.base_title)
            form.addRow("Source folder", source_row); form.addRow("Output folder", output_row)
            form.addRow("Target language", self.language); form.addRow(self.import_as_final); root.addLayout(form)
            actions = QHBoxLayout()
            analyze = QPushButton("Phân tích sequence"); analyze.clicked.connect(self._analyze)
            self.create_button = QPushButton("Tạo Series"); self.create_button.clicked.connect(self._create)
            actions.addWidget(analyze); actions.addWidget(self.create_button); actions.addStretch(1); root.addLayout(actions)
            self.analysis = QLabel("Chưa phân tích"); root.addWidget(self.analysis)
            self.series = QComboBox(); self.series.currentIndexChanged.connect(self._load_episodes); root.addWidget(self.series)
            delete_series = QPushButton("Xóa Series khỏi Content Library")
            delete_series.clicked.connect(self._delete_series); root.addWidget(delete_series)
            self.episodes = QTableWidget(0, 5)
            self.episodes.setHorizontalHeaderLabels(("Tập", "Filename", "Processing", "QA", "Final video"))
            self.episodes.horizontalHeader().setStretchLastSection(True)
            self.episodes.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            root.addWidget(self.episodes, 1)
            attach = QPushButton("Gắn final MP4 cho tập đã chọn"); attach.clicked.connect(self._attach_final); root.addWidget(attach)
            self.refresh()

        def refresh(self, selected_id: str | None = None) -> None:
            selected = selected_id or self.series.currentData()
            self.series.blockSignals(True); self.series.clear()
            for item in self.service.list_series(): self.series.addItem(item.name, item.id)
            self.series.blockSignals(False)
            index = self.series.findData(selected); self.series.setCurrentIndex(index if index >= 0 else 0)
            self._load_episodes()

        def _browse_source(self) -> None:
            path = QFileDialog.getExistingDirectory(self, "Chọn thư mục episode")
            if path:
                self.source_folder.setText(path)
                if not self.name.text().strip(): self.name.setText(Path(path).name)

        def _browse_output(self) -> None:
            path = QFileDialog.getExistingDirectory(self, "Chọn thư mục output")
            if path: self.output_folder.setText(path)

        def _analysis_text(self):
            result = self.service.analyze_folder(self.source_folder.text())
            duplicates = ", ".join(str(value) for value in sorted(result.duplicates)) or "không"
            missing = ", ".join(str(value) for value in result.missing) or "không"
            errors = " | ".join(result.errors) or "không"
            return result, f"Tìm thấy {len(result.episodes)} tập | Thiếu: {missing} | Trùng: {duplicates} | Lỗi: {errors}"

        def _analyze(self) -> None:
            try:
                _result, text = self._analysis_text(); self.analysis.setText(text)
            except Exception as exc: QMessageBox.critical(self, "Không thể phân tích", str(exc))

        def _create(self) -> None:
            self.create_button.setEnabled(False)
            try:
                result, text = self._analysis_text(); self.analysis.setText(text)
                if not result.valid: raise ValueError("Hãy sửa filename lỗi hoặc episode trùng trước khi tạo Series.")
                if result.missing and QMessageBox.question(
                    self, "Thiếu episode", f"Đang thiếu tập: {', '.join(map(str, result.missing))}. Vẫn tạo Series?",
                ) != QMessageBox.StandardButton.Yes: return
                series = self.service.create_series_from_folder(
                    name=self.name.text(), folder=self.source_folder.text(), base_title=self.base_title.text(),
                    target_language=str(self.language.currentData()), output_folder=self.output_folder.text(),
                    import_as_final=self.import_as_final.isChecked(),
                )
                self.refresh(series.id); self.library_changed.emit()
                QMessageBox.information(self, "Đã tạo Series", f"Đã import {len(result.episodes)} episode vào {series.name}.")
            except Exception as exc: QMessageBox.critical(self, "Không thể tạo Series", str(exc))
            finally: self.create_button.setEnabled(True)

        def _load_episodes(self) -> None:
            series_id = self.series.currentData(); rows = self.service.list_episodes(str(series_id)) if series_id else ()
            self.episodes.setRowCount(len(rows))
            for row, episode in enumerate(rows):
                number = QTableWidgetItem(str(episode.number)); number.setData(Qt.ItemDataRole.UserRole, episode.id)
                values = (number, QTableWidgetItem(episode.source_filename), QTableWidgetItem(episode.processing_status.value),
                          QTableWidgetItem(episode.qa_status), QTableWidgetItem(str(episode.final_video_path or "")))
                for column, value in enumerate(values): self.episodes.setItem(row, column, value)

        def _delete_series(self) -> None:
            series_id = self.series.currentData()
            if not series_id: return
            name = self.series.currentText()
            answer = QMessageBox.warning(
                self, "Xóa Series", f"Xóa '{name}' khỏi Content Library?\n\nCác file video trên ổ đĩa vẫn được giữ nguyên.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes: return
            try:
                self.service.delete_series(str(series_id)); self.refresh(); self.library_changed.emit()
            except Exception as exc: QMessageBox.critical(self, "Không thể xóa Series", str(exc))

        def _attach_final(self) -> None:
            row = self.episodes.currentRow()
            if row < 0:
                QMessageBox.information(self, "Chọn episode", "Hãy chọn một episode trước."); return
            path, _ = QFileDialog.getOpenFileName(self, "Chọn final video", "", "MP4 video (*.mp4)")
            if not path: return
            try:
                episode_id = str(self.episodes.item(row, 0).data(Qt.ItemDataRole.UserRole))
                self.service.register_final_video(episode_id, path)
                self._load_episodes(); self.library_changed.emit()
            except Exception as exc: QMessageBox.critical(self, "Không thể gắn video", str(exc))
else:
    class SeriesLibraryView:
        def __init__(self, *args, **kwargs): require_pyside6()
