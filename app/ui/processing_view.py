from __future__ import annotations

from .qt_compat import PYSIDE6_AVAILABLE, require_pyside6

STAGES = (
    "analyze_media", "detect_text_events", "ocr_events", "extract_audio", "asr",
    "classify_text_events", "erase_video", "translate_events", "render_final",
)

if PYSIDE6_AVAILABLE:
    from PySide6.QtWidgets import QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

    class ProcessingView(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            layout = QVBoxLayout(self)
            self.labels = {}
            for stage in STAGES:
                label = QLabel(f"○ {stage}")
                self.labels[stage] = label
                layout.addWidget(label)
            self.progress = QProgressBar()
            layout.addWidget(self.progress)
            self.job_status = QLabel("Job: idle")
            layout.addWidget(self.job_status)
            self.retry_button = QPushButton("Retry video lỗi/chưa xong")
            self.retry_button.setEnabled(False)
            layout.addWidget(self.retry_button)
            self.cancel_button = QPushButton("Dừng hàng đợi")
            self.cancel_button.setEnabled(False)
            layout.addWidget(self.cancel_button)

        def set_stage_event(self, event) -> None:
            for name, label in self.labels.items():
                if name == event.stage:
                    prefix = {"started": "◐", "completed": "✓", "failed": "✕"}.get(event.status.value, "○")
                    label.setText(f"{prefix} {name}")
            self.progress.setValue(int(round(event.progress * 100)))
            self.job_status.setText(f"Stage: {event.stage} — {event.status.value} {event.message}".strip())
            self.retry_button.setEnabled(event.status.value == "failed")
            self.cancel_button.setEnabled(event.status.value == "started")

        def set_job_record(self, record) -> None:
            self.job_status.setText(
                f"Job {record.id}: {record.stage} — {record.status.value} — attempt {record.attempts}"
            )
            self.progress.setValue(int(round(record.progress * 100)))
            self.retry_button.setEnabled(record.status.value == "failed")
            self.cancel_button.setEnabled(record.status.value == "running")
else:
    class ProcessingView:
        def __init__(self, *args, **kwargs):
            require_pyside6()
