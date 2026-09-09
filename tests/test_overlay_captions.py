import pytest
from app.core.subtitle_overlay.models import Cue, OverlayStyle
from app.core.subtitle_overlay.captions import read_cues, segment_cues
from app.core.subtitle_overlay.typography import FontMetrics, default_style


class Metrics:
    def width(self, text):
        return len(text) * 10


def test_split_keeps_every_word_and_original_interval():
    text = 'một hai ba bốn năm sáu bảy tám chín mười'
    displayed, warnings = segment_cues((Cue('a', 1000, 10000, text),), Metrics(), 100)
    assert ' '.join(word for cue in displayed for line in cue.lines for word in line.split()) == text
    assert all(1 <= len(cue.lines) <= 2 for cue in displayed)
    assert all(len(line)*10 <= 100 for cue in displayed for line in cue.lines)
    assert displayed[0].start_ms == 1000
    assert displayed[-1].end_ms == 10000
    assert all(a.end_ms == b.start_ms for a, b in zip(displayed, displayed[1:]))


def test_long_word_and_overlapping_input_rejected():
    with pytest.raises(ValueError):
        segment_cues((Cue('a', 0, 1000, 'unbreakable'),), Metrics(), 30)
    with pytest.raises(ValueError):
        segment_cues((Cue('a', 0, 1000, 'a'), Cue('b', 900, 1100, 'b')), Metrics(), 30)


def test_srt_and_ass_import_timing_and_no_overrides(tmp_path):
    srt = tmp_path / 'vi.srt'
    srt.write_text('1\n00:00:01,000 --> 00:00:03,500\nệ ợ ữ ậ ỗ ằ\n', encoding='utf-8')
    assert read_cues(srt)[0].end_ms == 3500
    ass = tmp_path / 'vi.ass'
    ass.write_text('[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n'
                   'Dialogue: 0,0:00:01.00,0:00:03.50,Default,,0,0,0,,{\\pos(1,2)}Xin, chào\\NViệt Nam\n')
    cue = read_cues(ass)[0]
    assert cue.text == 'Xin, chào Việt Nam'
    assert (cue.start_ms, cue.end_ms) == (1000, 3500)


def test_real_font_contains_double_diacritics():
    metrics = FontMetrics(default_style())
    assert metrics.has_glyphs('ệ ợ ữ ậ ỗ ằ')
    assert metrics.width('Việt Nam') > 0
    assert metrics.line_height > 48
