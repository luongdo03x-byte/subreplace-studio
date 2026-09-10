from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QPushButton, QSpinBox, QCheckBox, QScrollArea, QLineEdit, QFormLayout, QFileDialog)


class OverlayReviewView(QWidget):
    approve_requested = Signal(str, int, bool)
    approve_many_requested = Signal(object, bool)
    y_changed = Signal(str, int)
    style_changed = Signal(str, object)
    render_requested = Signal()
    resume_requested = Signal()
    retry_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        root = QVBoxLayout(self)
        root.addWidget(QLabel('Phụ đề Việt — duyệt vị trí cố định theo từng video nguồn'))
        self.status = QLabel('Chọn nhiều video ở Project, hoặc mở lại lô đã lưu.')
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        top = QHBoxLayout()
        self.sources = QListWidget()
        self.sources.setMaximumHeight(150)
        top.addWidget(self.sources, 1)
        self.y = QSpinBox(); self.y.setRange(0, 32000)
        self.apply_y = QPushButton('Áp dụng Y và tạo lại preview')
        controls = QVBoxLayout(); controls.addWidget(QLabel('Y tính từ đỉnh khung')); controls.addWidget(self.y); controls.addWidget(self.apply_y)
        top.addLayout(controls); root.addLayout(top)
        self.images = QHBoxLayout()
        image_widget = QWidget(); image_widget.setLayout(self.images)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(image_widget)
        root.addWidget(scroll, 1)
        self.warning_list = QListWidget(); self.warning_list.setMaximumHeight(100)
        root.addWidget(self.warning_list)
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
        self.style_button.setEnabled(bool(row and 'style' in row['payload']))

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
