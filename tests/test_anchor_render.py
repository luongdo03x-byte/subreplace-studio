"""Translated subtitles must render at a stable original subtitle position.

The source videos carry burned-in Chinese subtitles at ~2/3 frame height.
Rendering the Vietnamese replacement at the fixed bottom margin left both
visible ("lech"). Anchored segments share a median ASS \\pos to avoid jitter.
"""
from pathlib import Path

from app.core.rendering.ass import write_ass
from app.core.rendering.style import SubtitleStyle
from app.models.subtitle import SubtitleSegment


def _segment(anchor=None):
    return SubtitleSegment(
        id="s1", start_ms=1000, end_ms=2000,
        source_language="zh", source_text="放肆", target_language="vi",
        subtitle_optimized_translation="Lao xuong!", anchor=anchor,
    )


def _events_text(path):
    content = Path(path).read_text(encoding="utf-8")
    return [line for line in content.splitlines() if line.startswith("Dialogue:")]



def test_anchor_emits_pos(tmp_path):
    seg = _segment(anchor=(360, 905))
    write_ass(tmp_path / "a.ass", [seg], SubtitleStyle(), frame_size=(720, 1280))
    events = _events_text(tmp_path / "a.ass")
    assert len(events) == 1
    assert r"{\pos(360,905)" in events[0], events[0]


def test_no_anchor_keeps_bottom_margin(tmp_path):
    seg = _segment()
    write_ass(tmp_path / "b.ass", [seg], SubtitleStyle(), frame_size=(720, 1280))
    events = _events_text(tmp_path / "b.ass")
    assert len(events) == 1
    assert "\\pos(" not in events[0]


def test_anchor_clamped_to_frame(tmp_path):
    seg = _segment(anchor=(9999, 99999))
    write_ass(tmp_path / "c.ass", [seg], SubtitleStyle(), frame_size=(720, 1280))
    events = _events_text(tmp_path / "c.ass")
    assert r"{\pos(720,1280)" in events[0]


def test_segments_share_median_anchor(tmp_path):
    segments = [
        _segment(anchor=(300, 900)),
        _segment(anchor=(360, 910)),
        _segment(anchor=(500, 950)),
    ]
    write_ass(tmp_path / "d.ass", segments, SubtitleStyle(), frame_size=(720, 1280))
    events = _events_text(tmp_path / "d.ass")
    assert len(events) == 3
    assert all(r"{\pos(360,910)" in event for event in events)
