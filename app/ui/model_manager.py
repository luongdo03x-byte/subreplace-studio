from __future__ import annotations

from .qt_compat import PYSIDE6_AVAILABLE, require_pyside6

MODEL_COLUMNS = (
    "Provider", "Provider Version", "License", "Commercial", "Installed", "Accepted",
    "Component", "Component Version", "VRAM", "Path",
)

if PYSIDE6_AVAILABLE:
    from PySide6.QtWidgets import (
        QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTableWidget,
        QTableWidgetItem, QVBoxLayout, QWidget,
    )

    class ModelManagerView(QWidget):
        def __init__(self, parent=None, controller=None):
            super().__init__(parent)
            self.controller = controller
            layout = QVBoxLayout(self)
            layout.addWidget(QLabel("Model Manager — user-installed temporal AI providers and license status"))
            self.table = QTableWidget(0, len(MODEL_COLUMNS))
            self.table.setHorizontalHeaderLabels(list(MODEL_COLUMNS))
            self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            layout.addWidget(self.table)
            buttons = QHBoxLayout()
            self.select_plugin_button = QPushButton("Select plugin folder…")
            self.accept_button = QPushButton("Accept selected provider license")
            self.refresh_button = QPushButton("Refresh")
            buttons.addWidget(self.select_plugin_button)
            buttons.addWidget(self.accept_button)
            buttons.addWidget(self.refresh_button)
            layout.addLayout(buttons)
            self.select_plugin_button.clicked.connect(self._select_plugin_folder)
            self.accept_button.clicked.connect(self._accept_license)
            self.refresh_button.clicked.connect(self.refresh)
            self.refresh()

        def _selected_provider(self) -> str | None:
            row = self.table.currentRow()
            if row < 0:
                return None
            item = self.table.item(row, 0)
            return item.text() if item is not None else None

        def _select_plugin_folder(self) -> None:
            if self.controller is None:
                QMessageBox.warning(self, "Model Manager", "Model Manager backend is not configured.")
                return
            provider = self._selected_provider()
            if not provider:
                QMessageBox.information(self, "Model Manager", "Select a provider row first.")
                return
            if provider not in {"ProPainter", "E2FGVI", "STTN"}:
                QMessageBox.information(self, "Model Manager", f"{provider} is managed by the application runtime.")
                return
            path = QFileDialog.getExistingDirectory(self, f"Select {provider} plugin folder")
            if not path:
                return
            try:
                self.controller.set_plugin_path(provider, path)
                self.refresh()
            except Exception as exc:
                QMessageBox.critical(self, "Plugin folder rejected", str(exc))

        def _accept_license(self) -> None:
            if self.controller is None:
                return
            provider = self._selected_provider()
            if not provider:
                QMessageBox.information(self, "Model Manager", "Select a provider row first.")
                return
            try:
                status = next(item for item in self.controller.list_models() if item.name == provider)
            except StopIteration:
                QMessageBox.critical(self, "Model Manager", f"Unknown provider: {provider}")
                return
            if not status.user_install_required:
                QMessageBox.information(self, "License", f"{provider} does not require separate user acceptance.")
                return
            message = (
                f"Provider: {provider}\nLicense: {status.license_name}\n"
                f"Commercial use allowed: {status.commercial_use_allowed}\n\n"
                "By continuing, you confirm that you have reviewed and accept this provider license."
            )
            answer = QMessageBox.question(
                self, "Accept provider license", message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            try:
                self.controller.accept_license(provider)
                self.refresh()
            except Exception as exc:
                QMessageBox.critical(self, "License acceptance failed", str(exc))

        def refresh(self) -> None:
            if self.controller is None:
                self.table.setRowCount(0)
                return
            models = self.controller.list_models()
            self.table.setRowCount(len(models))
            for row, item in enumerate(models):
                values = (
                    item.name, item.version, item.license_name,
                    str(item.commercial_use_allowed),
                    "yes" if item.installed else "no",
                    "yes" if item.license_accepted else "no",
                    item.component_id or "—", item.component_version or "—",
                    f"{item.min_vram_mb} MB" if item.min_vram_mb is not None else "—",
                    str(item.component_path or item.plugin_path or "—"),
                )
                for column, value in enumerate(values):
                    self.table.setItem(row, column, QTableWidgetItem(value))
else:
    class ModelManagerView:
        def __init__(self, *args, **kwargs):
            require_pyside6()
