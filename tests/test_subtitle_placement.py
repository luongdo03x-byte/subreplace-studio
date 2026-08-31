"""Dat phu de Viet ngay duoi dai chu Trung ma khong chong len.

Neo bang \\an8 (dinh-giua) chu khong phai \\an2 (day-giua): toa do y khi do
la DINH khoi chu, nen no khong phu thuoc so dong. Cau 1 dong va cau 2 dong
bat dau o cung do cao, chu moc xuong duoi.
"""
from __future__ import annotations

import pytest

from app.core.rendering.placement import (
    ALIGN_TOP_CENTER,
    Placement,
    SubtitlePlacement,
    place_below_anchor,
)

FRAME = (720, 1280)


def test_text_starts_just_below_the_chinese_band():
    result = place_below_anchor((360, 800), line_count=1, font_size=42, frame_size=FRAME)
    assert result.alignment == ALIGN_TOP_CENTER
    assert result.x == 360
    assert result.y == 800 + round(42 * 0.45)
    assert result.font_size == 42
    assert result.clamped is False


def test_one_line_and_two_line_cues_start_at_the_same_height():
    one = place_below_anchor((360, 800), line_count=1, font_size=42, frame_size=FRAME)
    two = place_below_anchor((360, 800), line_count=2, font_size=42, frame_size=FRAME)
    assert one.y == two.y, "an8 anchors the top, so line count must not move it"


def test_font_shrinks_when_two_lines_do_not_fit_below():
    roomy = place_below_anchor((360, 700), line_count=2, font_size=42, frame_size=FRAME)
    tight = place_below_anchor((360, 1150), line_count=2, font_size=42, frame_size=FRAME)
    assert roomy.font_size == 42
    assert tight.font_size == 35
    assert tight.font_size >= round(42 * 0.78)


def test_gap_comes_from_the_base_size_so_the_top_never_moves():
    """Font size varies per cue; the gap must not, or tops drift between cues."""
    big = place_below_anchor((360, 800), line_count=1, font_size=42,
                             base_font_size=42, frame_size=FRAME)
    small = place_below_anchor((360, 800), line_count=2, font_size=33,
                               base_font_size=42, frame_size=FRAME)
    assert big.y == small.y == 800 + round(42 * 0.45)


def test_base_font_size_defaults_to_the_cue_font_size():
    assert (place_below_anchor((360, 800), line_count=1, font_size=42, frame_size=FRAME).y
            == place_below_anchor((360, 800), line_count=1, font_size=42,
                                  base_font_size=42, frame_size=FRAME).y)


def test_clamped_when_even_the_smallest_font_does_not_fit():
    result = place_below_anchor((360, 1270), line_count=2, font_size=42, frame_size=FRAME)
    assert result.clamped is True
    assert result.y + round(result.font_size * 1.2 * 2) <= FRAME[1]


def test_anchor_is_clamped_into_the_frame():
    result = place_below_anchor((9999, 99999), line_count=1, font_size=42, frame_size=FRAME)
    assert 0 <= result.x <= FRAME[0]
    assert 0 <= result.y <= FRAME[1]


def test_horizontal_position_follows_an_off_centre_source():
    result = place_below_anchor((250, 800), line_count=1, font_size=42, frame_size=FRAME)
    assert result.x == 250


@pytest.mark.parametrize("line_count", [0, -1])
def test_line_count_must_be_positive(line_count):
    with pytest.raises(ValueError):
        place_below_anchor((360, 800), line_count=line_count, font_size=42, frame_size=FRAME)


def test_placement_enum_values_are_stable_config_strings():
    assert SubtitlePlacement("on_anchor") is SubtitlePlacement.ON_ANCHOR
    assert SubtitlePlacement("below_anchor") is SubtitlePlacement.BELOW_ANCHOR


def test_placement_is_hashable_and_frozen():
    result = place_below_anchor((360, 800), line_count=1, font_size=42, frame_size=FRAME)
    assert isinstance(result, Placement)
    with pytest.raises(Exception):
        result.y = 5


@pytest.mark.parametrize("anchor_y", [700, 1100, 1159, 1200, 1258, 1279])
@pytest.mark.parametrize("base", [36, 42, 54])
def test_top_never_moves_across_the_fitting_clamp_boundary(anchor_y, base):
    """One anchor, one base size: every cue must share a top edge.

    anchor_y=1159 with base=54 previously straddled the boundary - a one-line
    cue fitted while a two-line cue clamped, giving two different tops.
    """
    ys = {
        place_below_anchor((360, anchor_y), line_count=lines, font_size=size,
                           base_font_size=base, frame_size=FRAME).y
        for lines in (1, 2)
        for size in range(round(base * 0.78), base + 1)
    }
    assert len(ys) == 1, f"drifted: {sorted(ys)}"


@pytest.mark.parametrize("anchor_y", [700, 1100, 1159, 1200, 1258, 1279])
def test_no_cue_ever_overflows_the_frame(anchor_y):
    for lines in (1, 2):
        for size in range(33, 43):
            spot = place_below_anchor((360, anchor_y), line_count=lines, font_size=size,
                                      base_font_size=42, frame_size=FRAME)
            assert spot.y + round(spot.font_size * 1.2 * lines) <= FRAME[1]


def test_clamped_cues_still_fit_inside_the_frame():
    for lines in (1, 2):
        for size in (42, 38, 33):
            spot = place_below_anchor((360, 1258), line_count=lines, font_size=size,
                                      base_font_size=42, frame_size=FRAME)
            assert spot.y + round(spot.font_size * 1.2 * lines) <= FRAME[1]


def test_fitting_path_invariant_is_unchanged():
    ys = {
        place_below_anchor((360, 800), line_count=lines, font_size=size,
                           base_font_size=42, frame_size=FRAME).y
        for lines in (1, 2)
        for size in (42, 38, 33)
    }
    assert len(ys) == 1
