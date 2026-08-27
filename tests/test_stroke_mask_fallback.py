"""generate_stroke_mask must cover glyphs even on busy backgrounds.

On test_60s.mp4 f681-696 (给哀家捏腰 over golden curtain texture) the
percentile+gradient mask came back empty -> eraser skipped 1074 frames.
Fallback: when the legacy mask is too sparse, derive a stroke-shaped mask
from Otsu polarity (glyph cluster), never a filled rectangle.
"""
import cv2
import numpy as np

from app.core.eraser.mask_generator import generate_stroke_mask
from app.workers.runner import _handle_protection_mask


def _busy_frame_with_text():
    rng = np.random.default_rng(11)
    h, w = 1280, 720
    yy, xx = np.mgrid[0:h, 0:w]
    base = 60 + (yy / h) * 90 + 25 * np.sin(xx / 17.0) + rng.normal(0, 6, (h, w))
    frame = np.clip(base, 0, 255).astype(np.uint8)
    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    # glyph strokes: thick white text with soft glow inside the bbox
    glyph = np.zeros((h, w), np.uint8)
    cv2.putText(glyph, "TEXT", (210, 860), cv2.FONT_HERSHEY_SIMPLEX, 2.4, 255, thickness=9)
    glow = cv2.GaussianBlur(glyph, (0, 0), 6)
    frame = np.clip(frame.astype(int) + (glow[..., None] * 1.4).astype(int) + (glyph[..., None] * 160), 0, 255).astype(np.uint8)
    return frame, glyph


def test_sparse_legacy_case_still_covers_glyphs():
    frame, glyph = _busy_frame_with_text()
    bbox = (150, 760, 420, 140)
    mask = generate_stroke_mask(frame, bbox)
    glyph_area = int(np.count_nonzero(glyph[bbox[1]:bbox[1]+bbox[3], bbox[0]:bbox[0]+bbox[2]]))
    covered = int(np.count_nonzero(mask[bbox[1]:bbox[1]+bbox[3], bbox[0]:bbox[0]+bbox[2]] & glyph[bbox[1]:bbox[1]+bbox[3], bbox[0]:bbox[0]+bbox[2]]))
    coverage = covered / max(1, glyph_area)
    assert coverage >= 0.60, f"mask covers only {coverage:.0%} of glyph pixels"


def test_mask_does_not_flood_background():
    frame, glyph = _busy_frame_with_text()
    bbox = (150, 760, 420, 140)
    mask = generate_stroke_mask(frame, bbox)
    roi_mask = mask[bbox[1]:bbox[1]+bbox[3], bbox[0]:bbox[0]+bbox[2]]
    roi_glyph = glyph[bbox[1]:bbox[1]+bbox[3], bbox[0]:bbox[0]+bbox[2]]
    bg_only = (roi_glyph == 0)
    flooded = float(np.count_nonzero(roi_mask[bg_only])) / max(1, int(np.count_nonzero(bg_only)))
    assert flooded <= 0.20, f"{flooded:.0%} of background pixels masked (flood)"


def test_clean_case_unchanged_behavior():
    # high contrast white text on flat dark background: legacy path already
    # works; result must stay sparse-and-precise, not a filled block.
    frame = np.zeros((1280, 720, 3), np.uint8)
    cv2.putText(frame, "ABC", (250, 900), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (255, 255, 255), 7)
    bbox = (240, 840, 240, 90)
    mask = generate_stroke_mask(frame, bbox)
    roi = mask[bbox[1]:bbox[1]+bbox[3], bbox[0]:bbox[0]+bbox[2]]
    filled = float(np.count_nonzero(roi)) / (bbox[2] * bbox[3])
    assert 0.03 <= filled <= 0.60, f"coverage {filled:.0%} outside expected stroke range"


def test_merged_handle_protection_excludes_cjk_tail():
    frame = np.zeros((180, 500, 3), np.uint8)
    cv2.putText(frame, "TG@svipk", (25, 115), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (210, 210, 210), 2)
    cv2.putText(frame, "BIG", (220, 125), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (255, 255, 255), 7)
    item = {"text": "TG@svipk中文字幕", "bbox": [0, 20, 500, 140]}
    protected = _handle_protection_mask(frame, item)
    assert np.count_nonzero(protected[:, 20:200]) > 0
    assert np.count_nonzero(protected[:, 220:]) == 0
