from pathlib import Path
import time
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QPushButton, QSpinBox, QCheckBox, QScrollArea, QLineEdit, QFormLayout, QFileDialog, QProgressBar)


class OverlayReviewView(QWidget):
    cancel_requested = Signal()
    approve_requested = Signal(str, int, bool)
    approve_many_requested = Signal(object, bool)
    y_changed = Signal(str, int)
    style_changed = Signal(str, object)
    render_requested = Signal()
    resume_requested = Signal()
    retry_requested = Signal()
    dubbing_changed = Signal(str, bool)
    save_y_default_requested = Signal(str, int)
    clear_y_default_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        root = QVBoxLayout(self)
        root.addWidget(QLabel('Phụ đề dịch — duyệt vị trí cố định theo từng video nguồn'))
        self.status = QLabel('Chọn nhiều video ở Project, hoặc mở lại lô đã lưu.')
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.hide()
        self.elapsed = QLabel()
        self.cancel_button = QPushButton('Dừng xử lý')
        self.cancel_button.hide()
        self.cancel_button.clicked.connect(self.cancel_requested.emit)
        root.addWidget(self.progress)
        root.addWidget(self.elapsed)
        root.addWidget(self.cancel_button)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self._busy_controls = []
        top = QHBoxLayout()
        self.sources = QListWidget()
        self.sources.setMaximumHeight(150)
        top.addWidget(self.sources, 1)
        self.y = QSpinBox(); self.y.setRange(0, 32000)
        self.apply_y = QPushButton('Áp dụng Y và tạo lại preview')
        controls = QVBoxLayout(); controls.addWidget(QLabel('Y tính từ đỉnh khung')); controls.addWidget(self.y); controls.addWidget(self.apply_y)
        self.save_y_default = QPushButton('Lưu Y cho video sau')
        self.clear_y_default = QPushButton('Dò Y tự động cho video sau')
        controls.addWidget(self.save_y_default); controls.addWidget(self.clear_y_default)
        self.save_y_default.clicked.connect(self._save_y_default)
        self.clear_y_default.clicked.connect(self.clear_y_default_requested.emit)
        top.addLayout(controls); root.addLayout(top)
        self.images = QHBoxLayout()
        image_widget = QWidget(); image_widget.setLayout(self.images)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(image_widget)
        root.addWidget(scroll, 1)
        self.warning_list = QListWidget(); self.warning_list.setMaximumHeight(100)
        root.addWidget(self.warning_list)
        audio_row = QHBoxLayout()
        self.dub_enabled = QCheckBox('Lồng tiếng theo ngôn ngữ đích (giảm giọng gốc khi đọc)')
        self.apply_dubbing = QPushButton('Áp dụng lồng tiếng và chuẩn bị lại')
        audio_row.addWidget(self.dub_enabled); audio_row.addWidget(self.apply_dubbing)
        root.addLayout(audio_row)
        self.apply_dubbing.clicked.connect(self._dubbing)
        form = QFormLayout()
        self.font_path = QLineEdit(); self.font_name = QLineEdit()
        self.font_size = QSpinBox(); self.font_size.setRange(8, 300); self.font_size.setValue(48)
        self.color = QLineEdit('&H00FFFFFF'); self.outline_color = QLineEdit('&H00000000')
        self.outline = QSpinBox(); self.outline.setRange(0, 20); self.outline.setValue(3)
        self.style_button = QPushButton('Áp dụng style cho nguồn này, duyệt lại')
        font_row = QHBoxLayout(); font_row.addWidget(self.font_path)
        browse = QPushButton('Chọn font'); font_row.addWidget(browse)
        browse.clicked.connect(self._browse_font)
        form.addRow('File font', font_row); form.addRow('Tên font', self.font_name)
        styles = QHBoxLayout()
        for label, widget in [('Cỡ', self.font_size), ('Màu ASS', self.color), ('Màu viền', self.outline_color), ('Viền', self.outline)]:
            styles.addWidget(QLabel(label)); styles.addWidget(widget)
        form.addRow(styles); root.addLayout(form); root.addWidget(self.style_button)
        self.fallback_confirm = QCheckBox('Tôi đã xem và chấp nhận các vị trí mặc định trong lô này')
        root.addWidget(self.fallback_confirm)
        actions = QHBoxLayout()
        self.approve_button = QPushButton('Duyệt nguồn đang chọn')
        self.approve_all = QPushButton('Duyệt các nguồn hợp lệ')
        self.render_button = QPushButton('Xuất video / gộp lô đã duyệt')
        reopen = QPushButton('Mở lại lô'); retry = QPushButton('Chuẩn bị lại / Retry')
        for button in (reopen, retry, self.approve_button, self.approve_all, self.render_button):
            actions.addWidget(button)
        root.addLayout(actions)
        self.sources.currentRowChanged.connect(self._selected)
        self.fallback_confirm.toggled.connect(self._buttons)
        self.apply_y.clicked.connect(self._apply_y)
        self.approve_button.clicked.connect(self._approve)
        self.approve_all.clicked.connect(self._approve_all)
        self.render_button.clicked.connect(self.render_requested.emit)
        reopen.clicked.connect(self.resume_requested.emit)
        retry.clicked.connect(self.retry_requested.emit)
        self.style_button.clicked.connect(self._style)
        self._buttons()

    def _tick(self):
        seconds = int(time.monotonic() - self._started)
        self.elapsed.setText(f'Đã chạy {seconds // 60:02d}:{seconds % 60:02d} — chưa có ước tính thời gian còn lại.')

    def begin_work(self, message):
        self.status.setText(message)
        self._started = time.monotonic()
        self.progress.setRange(0, 0)
        self.progress.show()
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()
        self._busy_controls = [(w, w.isEnabled()) for w in self.findChildren(QWidget)
                               if isinstance(w, (QPushButton, QSpinBox, QLineEdit, QCheckBox, QListWidget))
                               and w is not self.cancel_button]
        for widget, _ in self._busy_controls:
            widget.setEnabled(False)
        self._tick()
        self.timer.start()

    def end_work(self, message):
        self.timer.stop()
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.cancel_button.hide()
        for widget, enabled in self._busy_controls:
            widget.setEnabled(enabled)
        self._busy_controls = []
        seconds = int(time.monotonic() - self._started)
        self.elapsed.setText(f'Thời gian xử lý: {seconds // 60:02d}:{seconds % 60:02d}')
        self.status.setText(message)

    def show_sources(self, rows):
        index = max(0, self.sources.currentRow())
        self.rows = rows
        self.sources.blockSignals(True)
        self.sources.clear()
        for row in rows:
            self.sources.addItem(f"{row.get('name', row['id'])} — {row['state']} — v{row['revision']}")
        self.sources.blockSignals(False)
        self.sources.setCurrentRow(min(index, len(rows)-1))
        self._selected()

    def _current(self):
        index = self.sources.currentRow()
        return self.rows[index] if 0 <= index < len(self.rows) else None

    def _selected(self, *_):
        while self.images.count():
            item = self.images.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.warning_list.clear()
        row = self._current()
        if row:
            payload = row['payload']
            self.dub_enabled.setChecked(row.get('dub_enabled', bool(payload.get('dub_audio'))))
            self.dub_enabled.setEnabled(not row.get('external_subtitle', False))
            self.apply_dubbing.setEnabled(not row.get('external_subtitle', False))
            self.y.setValue(payload.get('layout', {}).get('y', 0))
            for preview in payload.get('previews', []):
                column = QWidget(); box = QVBoxLayout(column)
                caption = f"{preview['timestamp_ms']/1000:.2f}s" + (' — câu mẫu' if preview['sample_text'] else '')
                box.addWidget(QLabel(caption))
                label = QLabel(); pixmap = QPixmap(preview['path'])
                label.setPixmap(pixmap.scaled(300, 260, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                box.addWidget(label)
                self.images.addWidget(column)
            self.warning_list.addItems(payload.get('blocking', []) + payload.get('warnings', []))
            times = payload.get('collision_times', [])
            if times:
                self.warning_list.addItem('Chồng chữ tại: ' + ', '.join(f'{t/1000:.2f}s' for t in times[:15]))
            style = payload.get('style', {})
            self.font_path.setText(style.get('font_path', ''))
            self.font_name.setText(style.get('font_name', 'Be Vietnam Pro'))
            self.font_size.setValue(style.get('font_size', 48))
            self.color.setText(style.get('fill', '&H00FFFFFF'))
            self.outline_color.setText(style.get('outline_color', '&H00000000'))
            self.outline.setValue(style.get('outline', 3))
            profile = payload.get('profile', {})
            if profile:
                self.status.setText(f"Khung xuất {profile['width']}×{profile['height']}; thêm đệm, giữ Y riêng từng nguồn. "
                                    f"Nguồn này mở rộng {payload['layout']['extra_height']} px.")
        self._buttons()

    def _eligible(self, row):
        return (not row['payload'].get('blocking') and len(row['payload'].get('previews', [])) == 5
                and (not row['payload'].get('layout', {}).get('fallback') or self.fallback_confirm.isChecked()))

    def _buttons(self, *_):
        row = self._current()
        self.approve_button.setEnabled(bool(row and self._eligible(row)))
        self.approve_all.setEnabled(any(self._eligible(r) for r in self.rows))
        self.render_button.setEnabled(bool(self.rows) and all(not r['payload'].get('blocking')
            and r['approved'] == r['revision'] for r in self.rows))
        self.apply_y.setEnabled(bool(row and 'layout' in row['payload']))
        self.save_y_default.setEnabled(bool(row and 'info' in row['payload'] and 'layout' in row['payload']))
        self.style_button.setEnabled(bool(row and 'style' in row['payload']))
        self.apply_dubbing.setEnabled(bool(row and not row.get('external_subtitle', False)))

    def _dubbing(self):
        row = self._current()
        if row:
            self.dubbing_changed.emit(row['id'], self.dub_enabled.isChecked())

    def _save_y_default(self):
        row = self._current()
        if row:
            self.save_y_default_requested.emit(row['id'], self.y.value())

    def _approve(self):
        row = self._current()
        if row and self._eligible(row):
            self.approve_requested.emit(row['id'], row['revision'], self.fallback_confirm.isChecked())

    def _approve_all(self):
        self.approve_many_requested.emit([(r['id'], r['revision']) for r in self.rows if self._eligible(r)],
                                         self.fallback_confirm.isChecked())

    def _apply_y(self):
        row = self._current()
        if row:
            self.y_changed.emit(row['id'], self.y.value())

    def _browse_font(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Font tiếng Việt', '', 'Font (*.ttf *.otf)')
        if path:
            self.font_path.setText(path)

    def _style(self):
        row = self._current()
        if row:
            style = {**row['payload']['style'], 'font_path': self.font_path.text(),
                     'font_name': self.font_name.text(), 'font_size': self.font_size.value(),
                     'fill': self.color.text(), 'outline_color': self.outline_color.text(), 'outline': self.outline.value()}
            self.style_changed.emit(row['id'], style)
