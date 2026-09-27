from __future__ import annotations

from datetime import timezone
import threading
from zoneinfo import ZoneInfo

from .qt_compat import PYSIDE6_AVAILABLE, require_pyside6

if PYSIDE6_AVAILABLE:
    from PySide6.QtCore import QObject, QDateTime, Signal
    from PySide6.QtWidgets import (
        QCheckBox, QComboBox, QDateTimeEdit, QFileDialog, QFormLayout, QHBoxLayout,
        QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
        QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
    )

    from app.application.library_service import LibraryService
    from app.application.youtube_publishing import YouTubePublishingService
    from app.providers.youtube import YouTubePublisher


    class _YouTubeSignals(QObject):
        connected = Signal(object)
        progress = Signal(float)
        completed = Signal(str)
        failed = Signal(str)


    class YouTubePublishingView(QWidget):
        def __init__(self, library: LibraryService, parent=None):
            super().__init__(parent)
            self.library = library
            self.publisher = YouTubePublisher()
            self.service = YouTubePublishingService(library.store, self.publisher)
            self.signals = _YouTubeSignals()
            self.signals.connected.connect(self._connected)
            self.signals.progress.connect(lambda value: self.progress.setValue(round(value * 100)))
            self.signals.completed.connect(self._completed); self.signals.failed.connect(self._failed)
            self._account = None; self._busy = False
            root = QVBoxLayout(self)
            note = QLabel(
                "YouTube phase: OAuth Desktop App + resumable upload. TikTok và global Short sequence lock "
                "chưa được bật trong phase này. Upload có thể bị giới hạn private nếu Google API project chưa audit."
            )
            note.setWordWrap(True); root.addWidget(note)
            auth = QFormLayout(); self.client_secrets = QLineEdit()
            browse = QPushButton("Chọn client_secret.json…"); browse.clicked.connect(self._browse_client)
            auth_row = QHBoxLayout(); auth_row.addWidget(self.client_secrets, 1); auth_row.addWidget(browse)
            self.connect_button = QPushButton("Kết nối YouTube"); self.connect_button.clicked.connect(self._connect)
            reset = QPushButton("Đặt lại OAuth"); reset.clicked.connect(self._reset_auth)
            connect_row = QHBoxLayout(); connect_row.addWidget(self.connect_button); connect_row.addWidget(reset)
            self.account_label = QLabel("Chưa kết nối")
            auth.addRow("OAuth client", auth_row); auth.addRow("OAuth", connect_row)
            auth.addRow("Tài khoản", self.account_label); root.addLayout(auth)
            form = QFormLayout()
            self.series = QComboBox(); self.series.currentIndexChanged.connect(self._load_episodes)
            self.episode = QComboBox(); self.episode.currentIndexChanged.connect(self._fill_title)
            self.title = QLineEdit(); self.description = QPlainTextEdit(); self.description.setMaximumHeight(90)
            self.tags = QLineEdit(); self.tags.setPlaceholderText("tag1, tag2")
            self.privacy = QComboBox()
            for label, value in (("Private", "private"), ("Unlisted", "unlisted"), ("Public", "public")):
                self.privacy.addItem(label, value)
            self.use_schedule = QCheckBox("Đăng theo lịch YouTube")
            self.schedule = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
            self.schedule.setCalendarPopup(True); self.schedule.setDisplayFormat("yyyy-MM-dd HH:mm")
            self.timezone_name = QLineEdit("Asia/Ho_Chi_Minh")
            form.addRow("Series", self.series); form.addRow("Episode final", self.episode)
            form.addRow("Title", self.title); form.addRow("Description", self.description)
            form.addRow("Tags", self.tags); form.addRow("Visibility", self.privacy)
            form.addRow(self.use_schedule, self.schedule); form.addRow("Timezone", self.timezone_name); root.addLayout(form)
            self.upload_button = QPushButton("Tạo job và upload YouTube"); self.upload_button.clicked.connect(self._upload)
            self.progress = QProgressBar(); self.status = QLabel("Idle")
            root.addWidget(self.upload_button); root.addWidget(self.progress); root.addWidget(self.status)
            self.jobs = QTableWidget(0, 5)
            self.jobs.setHorizontalHeaderLabels(("Episode", "Status", "Remote ID", "Schedule", "Error"))
            self.jobs.horizontalHeader().setStretchLastSection(True); root.addWidget(self.jobs, 1)
            self.refresh()
            def restore_account():
                try: self.signals.connected.emit(self.publisher.account())
                except Exception: self.signals.connected.emit(None)
            self._start(restore_account)

        def refresh(self) -> None:
            selected = self.series.currentData(); self.series.blockSignals(True); self.series.clear()
            for item in self.library.list_series(): self.series.addItem(item.name, item.id)
            self.series.blockSignals(False)
            index = self.series.findData(selected); self.series.setCurrentIndex(index if index >= 0 else 0)
            self._load_episodes(); self._load_jobs()

        def _browse_client(self) -> None:
            path, _ = QFileDialog.getOpenFileName(self, "Google OAuth Desktop client", "", "JSON (*.json)")
            if path: self.client_secrets.setText(path)

        def _start(self, function) -> None:
            if self._busy: return
            self._busy = True; self.upload_button.setEnabled(False); self.connect_button.setEnabled(False)
            threading.Thread(target=function, daemon=True).start()

        def _reset_auth(self) -> None:
            self._busy = False; self.upload_button.setEnabled(True); self.connect_button.setEnabled(True)
            self.status.setText("OAuth đã đặt lại. Bấm Kết nối YouTube để thử lại.")

        def _connect(self) -> None:
            path = self.client_secrets.text().strip()
            def work():
                try: self.signals.connected.emit(self.publisher.connect(path))
                except Exception as exc: self.signals.failed.emit(str(exc))
            self._start(work)

        def _connected(self, account) -> None:
            self._busy = False; self.upload_button.setEnabled(True); self.connect_button.setEnabled(True)
            if account is None: return
            self._account = account
            self.account_label.setText(f"{account.title} ({account.channel_id})"); self.status.setText("YouTube connected")

        def _load_episodes(self) -> None:
            self.episode.clear(); series_id = self.series.currentData()
            if series_id:
                for item in self.library.list_episodes(str(series_id)):
                    if item.final_video_path is not None and item.qa_status == "pass":
                        self.episode.addItem(f"Tập {item.number} - {item.final_video_path.name}", item.id)
            self._fill_title()

        def _fill_title(self) -> None:
            series_id, episode_id = self.series.currentData(), self.episode.currentData()
            if not series_id or not episode_id: return
            series = self.library.store.get_series(str(series_id)); episode = self.library.store.get_episode(str(episode_id))
            self.title.setText(f"{series.base_title} tập {episode.number}")

        def _scheduled_at(self) -> str | None:
            if not self.use_schedule.isChecked(): return None
            zone = ZoneInfo(self.timezone_name.text().strip())
            local = self.schedule.dateTime().toPython().replace(tzinfo=zone)
            return local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

        def _upload(self) -> None:
            if self._account is None:
                QMessageBox.information(self, "YouTube", "Hãy kết nối tài khoản YouTube trước."); return
            episode_id = self.episode.currentData()
            if not episode_id:
                QMessageBox.information(self, "YouTube", "Chưa có episode với final MP4 và QA pass."); return
            try:
                job = self.library.create_youtube_job(
                    str(episode_id), account_id=self._account.channel_id, scheduled_at=self._scheduled_at(),
                    timezone_name=self.timezone_name.text().strip(), metadata={
                        "title": self.title.text(), "description": self.description.toPlainText(),
                        "tags": [value.strip() for value in self.tags.text().split(",") if value.strip()],
                        "privacy_status": str(self.privacy.currentData()), "category_id": "24",
                    },
                )
            except Exception as exc:
                QMessageBox.critical(self, "Không thể tạo YouTube job", str(exc)); return
            self.status.setText("Uploading…"); self.progress.setValue(0)
            def work():
                try: self.signals.completed.emit(self.service.publish(job.id, progress=self.signals.progress.emit))
                except Exception as exc: self.signals.failed.emit(str(exc))
            self._start(work)

        def _completed(self, remote_id: str) -> None:
            self._busy = False; self.upload_button.setEnabled(True); self.connect_button.setEnabled(True)
            self.status.setText(f"Uploaded: {remote_id}. YouTube đang xử lý."); self._load_jobs()

        def _failed(self, message: str) -> None:
            self._busy = False; self.upload_button.setEnabled(True); self.connect_button.setEnabled(True)
            self.status.setText(message); self._load_jobs()
            QMessageBox.critical(self, "YouTube", message)

        def _load_jobs(self) -> None:
            jobs = self.library.store.list_jobs(); self.jobs.setRowCount(len(jobs))
            for row, job in enumerate(jobs):
                episode = self.library.store.get_episode(job.episode_id)
                values = (str(episode.number), job.status.value, job.remote_id or "", job.scheduled_at or "", job.last_error or "")
                for column, value in enumerate(values): self.jobs.setItem(row, column, QTableWidgetItem(value))
else:
    class YouTubePublishingView:
        def __init__(self, *args, **kwargs): require_pyside6()
