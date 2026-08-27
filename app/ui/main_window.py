from __future__ import annotations

from pathlib import Path
import shutil

from .qt_compat import PYSIDE6_AVAILABLE, require_pyside6

if PYSIDE6_AVAILABLE:
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtWidgets import (
        QFileDialog, QHBoxLayout, QLabel, QListWidget, QMainWindow, QMessageBox, QPushButton,
        QStackedWidget, QVBoxLayout, QWidget,
    )
    from app.application.session import StudioSession
    from app.application.subtitle_document import SubtitleDocumentService
    from app.application.export_service import ExportService
    from app.application.model_manager_controller import ModelManagerController
    from app.application.view_model import PreflightFailedError, ProjectStartRequest, StudioViewModel
    from .export_dialog import ExportDialog
    from .diagnostics_view import DiagnosticsView
    from app.core.diagnostics import write_diagnostics
    from app.core.settings import app_data_root
    from .model_manager import ModelManagerView
    from .preview_view import PreviewView
    from .processing_view import ProcessingView
    from .project_setup import ProjectSetupView
    from .subtitle_editor import SubtitleEditorView

    class _UiSignals(QObject):
        stage_event = Signal(object)

    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("SubReplace Studio")
            self.resize(1440, 900)
            self.session = StudioSession()
            self.view_model = StudioViewModel(session=self.session)
            self.model_manager_controller = ModelManagerController()
            self.subtitle_documents = SubtitleDocumentService()
            self.export_service = ExportService()
            self.signals = _UiSignals()
            self.signals.stage_event.connect(self._on_stage_event)
            self._last_request: ProjectStartRequest | None = None
            self._output_dir: Path | None = None
            self._output_stem = "video"

            shell = QWidget(); root = QHBoxLayout(shell); sidebar = QVBoxLayout()
            brand = QLabel("SUBREPLACE STUDIO"); brand.setObjectName("brand"); sidebar.addWidget(brand)
            self.navigation = QListWidget(); self.stack = QStackedWidget()
            self.project_view = ProjectSetupView()
            self.processing_view = ProcessingView()
            self.preview_view = PreviewView()
            self.subtitle_editor = SubtitleEditorView()
            self.model_manager_view = ModelManagerView(controller=self.model_manager_controller)
            self.diagnostics_view = DiagnosticsView()
            pages = [
                ("Project", self.project_view), ("Process", self.processing_view),
                ("Preview", self.preview_view), ("Subtitle Editor", self.subtitle_editor),
                ("Model Manager", self.model_manager_view), ("Diagnostics", self.diagnostics_view),
            ]
            for name, widget in pages:
                self.navigation.addItem(name); self.stack.addWidget(widget)
            self.navigation.currentRowChanged.connect(self.stack.setCurrentIndex); self.navigation.setCurrentRow(0)
            sidebar.addWidget(self.navigation, 1)
            needs_review = QPushButton("Needs Review"); needs_review.clicked.connect(lambda: self.navigation.setCurrentRow(3)); sidebar.addWidget(needs_review)
            export = QPushButton("Export"); export.clicked.connect(self._show_export); sidebar.addWidget(export)
            side = QWidget(); side.setLayout(sidebar); side.setFixedWidth(220)
            root.addWidget(side); root.addWidget(self.stack, 1); self.setCentralWidget(shell)
            self.setStyleSheet(self._dark_theme())

            self.project_view.process_button.clicked.connect(self._start_processing)
            self.processing_view.cancel_button.clicked.connect(self._cancel_processing)
            self.processing_view.retry_button.clicked.connect(self._retry_processing)
            self.diagnostics_view.export_button.clicked.connect(self._export_diagnostics)
            self.subtitle_editor.refresh_button.clicked.connect(self._refresh_subtitles)
            self.subtitle_editor.save_button.clicked.connect(self._save_subtitle_edits)
            self.subtitle_editor.approve_dialogue_button.clicked.connect(
                lambda: self._set_review_decision("dialogue_subtitle")
            )
            self.subtitle_editor.keep_protected_button.clicked.connect(
                lambda: self._set_review_decision("scene_text")
            )

        def _request_from_form(self) -> ProjectStartRequest:
            view = self.project_view
            source_text = view.source_path.text().strip()
            source = Path(source_text) if source_text else Path("video.mp4")
            project_name = view.project_name.text().strip() or source.stem
            safe_name = "".join(char if char.isalnum() or char in "-_" else "-" for char in project_name).strip("-") or "video"
            project_parent = app_data_root() / "projects"
            project_root = project_parent / safe_name
            suffix = 2
            while project_root.exists() and any(project_root.iterdir()):
                project_root = project_parent / f"{safe_name}-{suffix}"
                suffix += 1
            self._output_dir = Path(view.project_root.text().strip() or (Path.home() / "Videos")).expanduser().resolve()
            self._output_stem = source.stem or safe_name
            temporal_provider = str(view.temporal_provider.currentData())
            repo_dir = view.temporal_repo_dir.text().strip()
            if not repo_dir and temporal_provider in {"propainter", "e2fgvi"}:
                stored = self.model_manager_controller.plugin_path("ProPainter" if temporal_provider == "propainter" else "E2FGVI")
                repo_dir = str(stored) if stored is not None else ""
            return ProjectStartRequest(
                source_path=source_text,
                project_root=str(project_root),
                project_name=project_name,
                target_language=str(view.target_language.currentData()),
                translation_provider=str(view.translation_provider.currentData()),
                translation_model=view.translation_model.text().strip(),
                endpoint=view.endpoint.text().strip(),
                api_key=view.api_key.text(),
                local_command=view.local_command.text().strip(),
                temporal_provider=temporal_provider,
                temporal_repo_dir=repo_dir,
                temporal_checkpoint=view.temporal_checkpoint.text().strip(),
                fp16=view.fp16.isChecked(),
            )

        def _start_processing(self) -> None:
            request = self._request_from_form()
            if not request.source_path:
                QMessageBox.warning(self, "Thiếu video", "Hãy chọn video cần dịch.")
                return
            if not self.project_view.save_api_key():
                QMessageBox.warning(self, "API key", "Không thể lưu API key vào kho mật khẩu; key vẫn dùng được cho lần chạy này.")
            try:
                handle, report = self.view_model.start(request, on_progress=self.signals.stage_event.emit)
            except PreflightFailedError as exc:
                details = "\n".join(f"{item.name}: {item.status.value} — {item.message}" for item in exc.report.checks)
                QMessageBox.critical(self, "Pre-flight failed", details)
                return
            except Exception as exc:
                QMessageBox.critical(self, "Cannot start project", str(exc))
                return
            self._last_request = request
            self.processing_view.cancel_button.setEnabled(True)
            self.navigation.setCurrentRow(1)
            self.diagnostics_view.set_report({
                "preflight": [
                    {"name": item.name, "status": item.status.value, "message": item.message}
                    for item in report.checks
                ],
                "job_id": handle.job_id,
            })

        def _retry_processing(self) -> None:
            request = self._last_request
            project = self.session.current_project
            handle = self.session.current_handle
            if request is None or project is None or handle is None:
                return
            try:
                translation = self.view_model._translation_config(request)
                temporal = self.view_model._temporal_config(request)
                has_audio = bool(self.view_model.media.probe(project.source_path).has_audio)
                self.session.retry_full(
                    project, handle.job_id,
                    translation_config=translation, temporal_config=temporal,
                    on_progress=self.signals.stage_event.emit,
                    has_audio=has_audio,
                )
                self.processing_view.retry_button.setEnabled(False)
                self.processing_view.cancel_button.setEnabled(True)
            except Exception as exc:
                QMessageBox.critical(self, "Retry failed", str(exc))

        def _cancel_processing(self) -> None:
            self.session.cancel()
            self.processing_view.cancel_button.setEnabled(False)
            self.processing_view.job_status.setText("Job: cancelling…")

        def _refresh_subtitles(self) -> None:
            project = self.session.current_project
            if project is None:
                self.subtitle_editor.set_rows(())
                return
            try:
                self.subtitle_editor.set_rows(self.subtitle_documents.load(project))
            except Exception as exc:
                QMessageBox.critical(self, "Cannot load subtitles", str(exc))

        def _save_subtitle_edits(self) -> None:
            project = self.session.current_project
            if project is None:
                return
            try:
                for segment_id, source_text, target_text in self.subtitle_editor.changed_rows():
                    if target_text is not None:
                        self.subtitle_documents.update_translation(project, segment_id, target_text)
                    if source_text is not None:
                        self.subtitle_documents.update_source_text(project, segment_id, source_text)
                self._refresh_subtitles()
            except Exception as exc:
                QMessageBox.critical(self, "Cannot save subtitle edits", str(exc))

        def _set_review_decision(self, text_type: str) -> None:
            project = self.session.current_project
            segment_id = self.subtitle_editor.require_selection()
            if project is None or segment_id is None:
                return
            try:
                self.subtitle_documents.set_review_decision(project, segment_id, text_type=text_type)
                self._refresh_subtitles()
            except Exception as exc:
                QMessageBox.critical(self, "Cannot update review", str(exc))

        def _on_stage_event(self, event) -> None:
            self.processing_view.set_stage_event(event)
            if event.status.value == "completed" and event.stage in {"classify_text_events", "translate_events"}:
                self._refresh_subtitles()
            if event.status.value == "completed" and event.stage == "render_final":
                self.processing_view.cancel_button.setEnabled(False)
                project = self.session.current_project
                if project is not None:
                    final = project.root / "exports" / f"final_{project.target_language}.mp4"
                    self.preview_view.set_sources(project.source_path, final if final.is_file() else None)
                    self._refresh_subtitles()
                    published = final
                    if final.is_file() and self._output_dir is not None:
                        self._output_dir.mkdir(parents=True, exist_ok=True)
                        published = self._output_dir / f"{self._output_stem}_{project.target_language}.mp4"
                        shutil.copy2(final, published)
                        # The MP4 already contains burned-in subtitles. A
                        # matching sidecar makes players such as VLC show it twice.
                        published.with_suffix(".srt").unlink(missing_ok=True)
                    QMessageBox.information(self, "Hoàn tất", f"Video đã dịch: {published}")

        def _show_export(self):
            project = self.session.current_project
            if project is None:
                QMessageBox.information(self, "No project", "Open or process a project before exporting.")
                return
            dialog = ExportDialog(self, default_output=str(project.root / "exports"))
            if not dialog.exec():
                return
            output = dialog.output_path.text().strip()
            if not output:
                return
            try:
                result = self.export_service.export(
                    project, output,
                    include_subtitle=dialog.export_subtitle.isChecked(),
                    include_clean=dialog.export_clean.isChecked(),
                    include_project=dialog.export_project.isChecked(),
                )
                QMessageBox.information(self, "Export completed", f"Exported {len(result.files)} files to {result.output_dir}")
            except Exception as exc:
                QMessageBox.critical(self, "Export failed", str(exc))

        def _export_diagnostics(self) -> None:
            suggested = "subreplace-diagnostics.json"
            path, _ = QFileDialog.getSaveFileName(self, "Export diagnostics", suggested, "JSON (*.json)")
            if not path:
                return
            try:
                write_diagnostics(
                    path,
                    model_manager=self.model_manager_controller.service(),
                    project=self.session.current_project,
                    job_store=self.session.current_handle.job_store if self.session.current_handle is not None else None,
                )
                QMessageBox.information(self, "Diagnostics exported", path)
            except Exception as exc:
                QMessageBox.critical(self, "Diagnostics export failed", str(exc))

        @staticmethod
        def _dark_theme() -> str:
            return """
                QMainWindow,QWidget { background:#0A0F18; color:#E7ECF4; font-size:13px; }
                #brand { font-weight:700; font-size:16px; padding:12px 6px; }
                QListWidget { background:#0E1623; border:1px solid #243043; border-radius:10px; padding:5px; }
                QListWidget::item { padding:10px; border-radius:7px; }
                QListWidget::item:selected { background:#3656D4; color:white; }
                QPushButton { background:#182235; border:1px solid #30405A; padding:9px 12px; border-radius:8px; }
                QPushButton:hover { background:#22304A; }
                QTableWidget,QLineEdit,QComboBox { background:#0D1522; border:1px solid #27364D; border-radius:6px; }
            """
else:
    class MainWindow:
        def __init__(self, *args, **kwargs):
            require_pyside6()
