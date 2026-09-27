import math
import os
from pathlib import Path
import unicodedata
from .models import OverlayStyle

_application = None


def default_style():
    return OverlayStyle(Path(__file__).resolve().parents[2] / 'assets/fonts/BeVietnamPro-Regular.ttf')


class FontMetrics:
    def __init__(self, style):
        from PySide6.QtGui import QGuiApplication, QFontDatabase, QFont, QFontMetricsF
        from PySide6.QtWidgets import QApplication
        global _application
        if not style.font_path.is_file():
            raise ValueError(f'Không tìm thấy font: {style.font_path}')
        if not 8 <= style.font_size <= 300 or min(style.outline, style.shadow, style.margin_x) < 0:
            raise ValueError('Invalid subtitle style dimensions')
        if QGuiApplication.instance() is None:
            os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
            _application = QApplication([])
        font_id = QFontDatabase.addApplicationFont(str(style.font_path))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if style.font_name not in families:
            raise ValueError('Tên font không khớp với file font đã chọn')
        font = QFont(style.font_name)
        font.setPixelSize(style.font_size)
        font.setStyleStrategy(QFont.StyleStrategy.NoFontMerging)
        self.metrics = QFontMetricsF(font)
        self.line_height = math.ceil(self.metrics.height() + self.metrics.leading() + 2 * style.outline + style.shadow)

    def width(self, text):
        return self.metrics.horizontalAdvance(unicodedata.normalize('NFC', text))

    def has_glyphs(self, text):
        return all(c.isspace() or self.metrics.inFontUcs4(ord(c)) for c in unicodedata.normalize('NFC', text))


def style_for_language(style, language):
    """Choose installed fonts for scripts absent from the bundled Latin font."""
    from dataclasses import replace
    fonts = {
        'ja': ('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', 'Noto Sans CJK JP'),
        'ko': ('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', 'Noto Sans CJK KR'),
        'th': ('/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf', 'Noto Sans Thai'),
    }
    if language not in fonts or style.font_name != 'Be Vietnam Pro':
        return style
    path, family = fonts[language]
    if not Path(path).is_file():
        raise ValueError(f'Cần cài font {family} để xuất phụ đề ngôn ngữ này.')
    return replace(style, font_path=Path(path), font_name=family)
