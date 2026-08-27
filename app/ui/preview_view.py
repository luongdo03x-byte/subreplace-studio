from __future__ import annotations

from .qt_compat import PYSIDE6_AVAILABLE, require_pyside6

if PYSIDE6_AVAILABLE:
    from PySide6.QtCore import QUrl, Qt
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
    from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

    from app.application.preview_sync import sync_target_position

    class PreviewView(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            root = QVBoxLayout(self)
            videos = QHBoxLayout()

            self.original_video = QVideoWidget()
            self.replaced_video = QVideoWidget()
            self.original_video.setMinimumSize(320, 180)
            self.replaced_video.setMinimumSize(320, 180)

            for title, widget in (("Original", self.original_video), ("Replaced", self.replaced_video)):
                column = QVBoxLayout()
                column.addWidget(QLabel(title))
                column.addWidget(widget, 1)
                videos.addLayout(column, 1)
            root.addLayout(videos, 1)

            controls = QHBoxLayout()
            self.play_button = QPushButton("Play")
            self.seek = QSlider(Qt.Orientation.Horizontal)
            self.seek.setRange(0, 0)
            self.time_label = QLabel("00:00 / 00:00")
            controls.addWidget(self.play_button)
            controls.addWidget(self.seek, 1)
            controls.addWidget(self.time_label)
            root.addLayout(controls)

            self.original_player = QMediaPlayer(self)
            self.replaced_player = QMediaPlayer(self)
            self.audio = QAudioOutput(self)
            self.original_player.setAudioOutput(self.audio)
            self.replaced_audio = QAudioOutput(self)
            self.replaced_audio.setMuted(True)
            self.replaced_player.setAudioOutput(self.replaced_audio)
            self.original_player.setVideoOutput(self.original_video)
            self.replaced_player.setVideoOutput(self.replaced_video)

            self.play_button.clicked.connect(self.toggle_playback)
            self.seek.sliderMoved.connect(self.seek_to)
            self.original_player.positionChanged.connect(self._on_position)
            self.original_player.durationChanged.connect(self._on_duration)
            self.original_player.playbackStateChanged.connect(self._on_state)

        def set_sources(self, original, replaced=None) -> None:
            original_path = str(original) if original else ""
            replaced_path = str(replaced) if replaced else ""
            self.original_player.stop()
            self.replaced_player.stop()
            self.original_player.setSource(QUrl.fromLocalFile(original_path) if original_path else QUrl())
            self.replaced_player.setSource(QUrl.fromLocalFile(replaced_path) if replaced_path else QUrl())
            self.seek.setValue(0)

        def toggle_playback(self) -> None:
            if self.original_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.original_player.pause()
                self.replaced_player.pause()
            else:
                position = self.original_player.position()
                self.replaced_player.setPosition(position)
                self.original_player.play()
                self.replaced_player.play()

        def seek_to(self, position: int) -> None:
            self.original_player.setPosition(position)
            self.replaced_player.setPosition(position)

        def _on_position(self, position: int) -> None:
            if not self.seek.isSliderDown():
                self.seek.setValue(position)
            correction = sync_target_position(position, self.replaced_player.position())
            if correction is not None:
                self.replaced_player.setPosition(correction)
            self._update_time(position, self.original_player.duration())

        def _on_duration(self, duration: int) -> None:
            self.seek.setRange(0, max(0, duration))
            self._update_time(self.original_player.position(), duration)

        def _on_state(self, state) -> None:
            playing = state == QMediaPlayer.PlaybackState.PlayingState
            self.play_button.setText("Pause" if playing else "Play")
            if not playing and self.replaced_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.replaced_player.pause()

        def _update_time(self, position: int, duration: int) -> None:
            self.time_label.setText(f"{self._clock(position)} / {self._clock(duration)}")

        @staticmethod
        def _clock(milliseconds: int) -> str:
            total = max(0, int(milliseconds)) // 1000
            minutes, seconds = divmod(total, 60)
            hours, minutes = divmod(minutes, 60)
            if hours:
                return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            return f"{minutes:02d}:{seconds:02d}"
else:
    class PreviewView:
        def __init__(self, *args, **kwargs):
            require_pyside6()
