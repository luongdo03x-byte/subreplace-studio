"""Where the translated subtitle sits relative to the burned-in source text."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# ASS numpad alignment: 2 is bottom-centre, 8 is top-centre.
ALIGN_BOTTOM_CENTER = 2
ALIGN_TOP_CENTER = 8


class SubtitlePlacement(str, Enum):
    ON_ANCHOR = "on_anchor"
    BELOW_ANCHOR = "below_anchor"


@dataclass(frozen=True, slots=True)
class Placement:
    x: int
    y: int
    font_size: int
    alignment: int
    clamped: bool = False


def place_below_anchor(
    anchor: tuple[int, int],
    *,
    line_count: int,
    font_size: int,
    frame_size: tuple[int, int],
    base_font_size: int | None = None,
    gap_ratio: float = 0.45,
    line_height: float = 1.2,
    min_font_scale: float = 0.78,
    bottom_safe_ratio: float = 0.02,
) -> Placement:
    """Anchor the top of the translated block just under the source subtitle.

    Using \\an8 makes the returned y the TOP of the text block, so it is
    independent of line count: one-line and two-line cues start at the same
    height and grow downward, away from the Chinese text.

    The gap is measured from base_font_size, not the cue's own size. Layout
    already shrinks long cues to fit the frame width, so deriving the gap
    from the shrunken size would drift the top between cues - the exact
    jitter \\an8 is here to prevent.
    """
    if line_count <= 0:
        raise ValueError("line_count must be positive")
    if font_size <= 0:
        raise ValueError("font_size must be positive")
    width, height = frame_size
    x = min(max(0, int(anchor[0])), width)
    baseline = min(max(0, int(anchor[1])), height)
    top = min(baseline + round((base_font_size or font_size) * gap_ratio), height)
    limit = height - round(height * bottom_safe_ratio)
    floor_size = max(1, round(font_size * min_font_scale))

    for size in range(font_size, floor_size - 1, -1):
        if top + round(size * line_height * line_count) <= limit:
            return Placement(x=x, y=top, font_size=size, alignment=ALIGN_TOP_CENTER)

    block = round(floor_size * line_height * line_count)
    return Placement(x=x, y=min(top, max(0, height - block)),
                     font_size=floor_size, alignment=ALIGN_TOP_CENTER, clamped=True)
