"""Khong xoa chu Trung nua, nen chu Viet phai nam duoi no."""
from __future__ import annotations

import re
from pathlib import Path

from app.core.rendering.ass import write_ass
from app.core.rendering.placement import SubtitlePlacement
from app.core.rendering.style import SubtitleStyle
from app.models.subtitle import SubtitleSegment


def _segment(text="Lao xuong!", anchor=None):
    return SubtitleSegment(
        id="s1", start_ms=1000, end_ms=2000,
        source_language="zh", source_text="fang si", target_language="vi",
        subtitle_optimized_translation=text, anchor=anchor,
    )


def _events(path):
    return [line for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.startswith("Dialogue:")]


def _pos(event):
    match = re.search(r"\\pos\((\d+),(\d+)\)", event)
    assert match, event
    return int(match.group(1)), int(match.group(2))


def test_below_anchor_emits_top_centre_alignment(tmp_path):
    write_ass(tmp_path / "a.ass", [_segment(anchor=(360, 800))], SubtitleStyle(),
              frame_size=(720, 1280), placement=SubtitlePlacement.BELOW_ANCHOR)
    event = _events(tmp_path / "a.ass")[0]
    assert r"\an8" in event
    _, y = _pos(event)
    assert y > 800, "translated text must start below the source subtitle"


def test_on_anchor_keeps_the_original_overlapping_position(tmp_path):
    write_ass(tmp_path / "b.ass", [_segment(anchor=(360, 905))], SubtitleStyle(),
              frame_size=(720, 1280), placement=SubtitlePlacement.ON_ANCHOR)
    event = _events(tmp_path / "b.ass")[0]
    assert r"\an8" not in event
    assert _pos(event) == (360, 905)


def test_one_and_two_line_cues_share_the_same_top(tmp_path):
    short = _segment(text="Ngan", anchor=(360, 800))
    long_text = _segment(text=" ".join(["motu"] * 30), anchor=(360, 800))
    write_ass(tmp_path / "c.ass", [short, long_text], SubtitleStyle(),
              frame_size=(720, 1280), placement=SubtitlePlacement.BELOW_ANCHOR)
    events = _events(tmp_path / "c.ass")
    assert len(events) == 2
    assert _pos(events[0])[1] == _pos(events[1])[1]


def test_below_anchor_without_any_anchor_falls_back_to_style_margin(tmp_path):
    write_ass(tmp_path / "d.ass", [_segment()], SubtitleStyle(),
              frame_size=(720, 1280), placement=SubtitlePlacement.BELOW_ANCHOR)
    event = _events(tmp_path / "d.ass")[0]
    assert r"\pos(" not in event
    assert r"\an8" not in event


def test_style_defaults_use_a_heavier_outline_for_unerased_video():
    style = SubtitleStyle()
    assert style.outline_width == 2.5
    assert style.shadow == 1.0


def test_style_header_carries_the_heavier_outline(tmp_path):
    write_ass(tmp_path / "e.ass", [_segment(anchor=(360, 800))], SubtitleStyle(),
              frame_size=(720, 1280), placement=SubtitlePlacement.BELOW_ANCHOR)
    content = (tmp_path / "e.ass").read_text(encoding="utf-8")
    style_line = next(line for line in content.splitlines() if line.startswith("Style: Default"))
    assert ",2.5,1.0," in style_line


def test_write_ass_reports_what_it_did_for_diagnostics(tmp_path):
    report = write_ass(tmp_path / "f.ass", [_segment(anchor=(360, 800))], SubtitleStyle(),
                       frame_size=(720, 1280), placement=SubtitlePlacement.BELOW_ANCHOR)
    assert report["placement"] == "below_anchor"
    assert report["anchor"] == [360, 800]
    assert report["frame_size"] == [720, 1280]
    assert report["clamped"] is False
    assert report["min_font_size"] == 42


def test_write_ass_reports_clamping_when_there_is_no_room(tmp_path):
    # A two-line cue anchored right at the bottom of the frame leaves no room
    # to shrink into - even the floor font size cannot fit both lines above
    # the bottom-safe margin, so the report must say so.
    two_line_text = "Chung ta phai lao xuong ngay bay gio truoc khi qua muon"
    report = write_ass(tmp_path / "g.ass", [_segment(text=two_line_text, anchor=(360, 1275))],
                       SubtitleStyle(), frame_size=(720, 1280),
                       placement=SubtitlePlacement.BELOW_ANCHOR)
    assert report["clamped"] is True


def test_write_ass_report_without_an_anchor_says_so(tmp_path):
    report = write_ass(tmp_path / "h.ass", [_segment()], SubtitleStyle(),
                       frame_size=(720, 1280), placement=SubtitlePlacement.BELOW_ANCHOR)
    assert report["anchor"] is None
    assert report["clamped"] is False
