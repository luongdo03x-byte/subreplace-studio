from __future__ import annotations

from .qt_compat import PYSIDE6_AVAILABLE, require_pyside6

if PYSIDE6_AVAILABLE:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QAbstractItemView, QHBoxLayout, QLabel, QMessageBox, QPushButton,
        QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
    )

    class SubtitleEditorView(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            layout = QVBoxLayout(self)
            layout.addWidget(QLabel("Subtitle Editor — edit OCR/translation and resolve Needs Review items"))
            self.table = QTableWidget(0, 7)
            self.table.setHorizontalHeaderLabels([
                "Chinese", "Translation", "Type", "Status", "OCR", "Classifier", "ID"
            ])
            self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            self.table.setColumnHidden(6, True)
            self.table.horizontalHeader().setStretchLastSection(False)
            self.table.horizontalHeader().setSectionResizeMode(0, self.table.horizontalHeader().ResizeMode.Stretch)
            self.table.horizontalHeader().setSectionResizeMode(1, self.table.horizontalHeader().ResizeMode.Stretch)
            layout.addWidget(self.table, 1)

            actions = QHBoxLayout()
            self.save_button = QPushButton("Save Edits")
            self.approve_dialogue_button = QPushButton("Approve as Dialogue")
            self.keep_protected_button = QPushButton("Keep Protected")
            self.refresh_button = QPushButton("Refresh")
            for button in (self.save_button, self.approve_dialogue_button, self.keep_protected_button, self.refresh_button):
                actions.addWidget(button)
            actions.addStretch(1)
            layout.addLayout(actions)
            self._baseline: dict[str, tuple[str, str]] = {}

        def set_rows(self, rows) -> None:
            self.table.setRowCount(0)
            self._baseline.clear()
            for row in rows:
                index = self.table.rowCount()
                self.table.insertRow(index)
                source = QTableWidgetItem(row.source_text)
                source.setData(Qt.ItemDataRole.UserRole, row.id)
                target = QTableWidgetItem(row.target_text)
                text_type = QTableWidgetItem(row.text_type)
                status = QTableWidgetItem(row.review_status)
                ocr = QTableWidgetItem(f"{row.ocr_confidence:.2f}")
                classifier = QTableWidgetItem(f"{row.classification_confidence:.2f}")
                identifier = QTableWidgetItem(row.id)
                for item in (text_type, status, ocr, classifier, identifier):
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if row.review_status == "needs_review":
                    status.setToolTip("This item is protected until you approve it as dialogue or keep it protected.")
                for col, item in enumerate((source, target, text_type, status, ocr, classifier, identifier)):
                    self.table.setItem(index, col, item)
                self._baseline[row.id] = (row.source_text, row.target_text)
            self.table.resizeColumnsToContents()

        def selected_segment_id(self) -> str | None:
            row = self.table.currentRow()
            if row < 0:
                return None
            item = self.table.item(row, 0)
            if item is None:
                return None
            value = item.data(Qt.ItemDataRole.UserRole)
            return str(value) if value else None

        def changed_rows(self) -> tuple[tuple[str, str | None, str | None], ...]:
            changes = []
            for row in range(self.table.rowCount()):
                source_item = self.table.item(row, 0)
                target_item = self.table.item(row, 1)
                if source_item is None:
                    continue
                identifier = str(source_item.data(Qt.ItemDataRole.UserRole) or "")
                original_source, original_target = self._baseline.get(identifier, ("", ""))
                source_text = source_item.text().strip()
                target_text = target_item.text().strip() if target_item is not None else ""
                changes.append((
                    identifier,
                    source_text if source_text != original_source else None,
                    target_text if target_text != original_target else None,
                ))
            return tuple(item for item in changes if item[1] is not None or item[2] is not None)

        def require_selection(self) -> str | None:
            identifier = self.selected_segment_id()
            if identifier is None:
                QMessageBox.information(self, "Select subtitle", "Select a subtitle row first.")
            return identifier
else:
    class SubtitleEditorView:
        def __init__(self, *args, **kwargs):
            require_pyside6()
