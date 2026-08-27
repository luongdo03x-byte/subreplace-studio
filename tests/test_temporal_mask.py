"""Static subtitle on moving background: temporal-min isolates glyphs.

给哀家捏腰 sits over swaying bead-curtain texture. Per-frame masks catch
bead highlights (flood) or only glyph cores (ghost text). The event's own
frames share a static text layer while the background moves, so the
per-pixel minimum over the event's frames suppresses the background and
keeps the glyphs.
"""
import numpy as np

from app.core.eraser.mask_generator import temporal_stroke_mask


def _frames_with_static_text(moving_dots=True):
    rng = np.random.default_rng(3)
    frames = []
    yy, xx = np.mgrid[0:1280, 0:720]
    base = (70 + (yy / 1280) * 100 + 30 * np.sin(xx / 13.0)).astype(np.uint8)
    for t in range(6):
        frame = cv2.cvtColor(np.clip(base + rng.normal(0, 7, base.shape), 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
        if moving_dots:
            # bright shimmering specks (beads) at random positions each frame
            xs = rng.integers(150, 570, 220)
            ys = rng.integers(740, 990, 220)
            for x, y in zip(xs, ys):
                frame[y:y+3, x:x+3] = (250, 240, 220)
        frame = frame.copy()
        # static white subtitle glyphs
        cv2.putText(frame, "NIAN YAO", (215, 900), cv2.FONT_HERSHEY_SIMPLEX, 1.9, (255, 255, 255), 8)
        frames.append(frame)
    return frames


import cv2


def test_temporal_mask_covers_glyphs_and_rejects_shimmer():
    frames = _frames_with_static_text()
    bbox = (200, 780, 330, 160)
    mask = temporal_stroke_mask([f[bbox[1]:bbox[1]+bbox[3], bbox[0]:bbox[0]+bbox[2]] for f in frames])
    x0, y0, w, h = 0, 0, bbox[2], bbox[3]
    # glyph reference: text is static -> present in every frame at same spot
    glyph = cv2.cvtColor(frames[0][bbox[1]:bbox[1]+bbox[3], bbox[0]:bbox[0]+bbox[2]], cv2.COLOR_BGR2GRAY) > 200
    coverage = np.count_nonzero(mask[glyph > 0]) / max(1, np.count_nonzero(glyph))
    bg = glyph == 0
    flood = np.count_nonzero(mask[bg > 0]) / max(1, np.count_nonzero(bg))
    assert coverage >= 0.55, f"glyph coverage {coverage:.0%}"
    assert flood <= 0.15, f"background flood {flood:.0%}"


def test_single_frame_fallback_matches_per_frame():
    frames = _frames_with_static_text(moving_dots=False)
    bbox = (200, 780, 330, 160)
    m1 = temporal_stroke_mask([frames[0][bbox[1]:bbox[1]+bbox[3], bbox[0]:bbox[0]+bbox[2]]])
    from app.core.eraser.mask_generator import generate_stroke_mask
    m2 = generate_stroke_mask(frames[0], bbox)
    # border dilation context differs (full frame vs ROI); compare interior
    assert np.array_equal(m1[20:-20, 20:-20], m2[bbox[1]+20:bbox[1]+bbox[3]-20, bbox[0]+20:bbox[0]+bbox[2]-20])


def test_glyph_presence_delta_tracks_text():
    import cv2
    from app.workers.runner import _glyph_presence_delta
    frames = _frames_with_static_text()
    bbox = (200, 780, 330, 160)
    from app.core.eraser.mask_generator import temporal_stroke_mask
    m = temporal_stroke_mask([f[bbox[1]:bbox[1]+bbox[3], bbox[0]:bbox[0]+bbox[2]] for f in frames[:4]], dilate=False)
    full = np.zeros(frames[0].shape[:2], np.uint8)
    full[bbox[1]:bbox[1]+m.shape[0], bbox[0]:bbox[0]+m.shape[1]] = m
    # blank frame with same background stats -> no text
    blank = np.full(frames[0].shape, 90, np.uint8)
    assert _glyph_presence_delta(frames[0], full) > _glyph_presence_delta(blank, full) + 0.5


def test_residual_text_is_rejected_after_high_ring_error(monkeypatch):
    """Noisy reconstruction must not be accepted merely due to a high ring error."""
    import cv2
    from app.core.eraser import pipeline
    from app.core.eraser.pipeline import ClassicalEraser

    base = np.tile(np.linspace(60, 140, 960).astype(np.uint8), (1280, 1))
    frame = cv2.cvtColor(base, cv2.COLOR_GRAY2BGR)
    cv2.putText(frame, "TEST", (300, 880), cv2.FONT_HERSHEY_SIMPLEX, 3.0, (255, 255, 255), 14)
    mask = np.zeros((1280, 960), np.uint8)
    cv2.putText(mask, "TEST", (300, 880), cv2.FONT_HERSHEY_SIMPLEX, 3.0, 255, 16)
    # refs: same background statistics, heavy decorrelated noise -> ring
    # error stays above the acceptance band while the fused background
    # still erases the glyphs.
    rng = np.random.default_rng(7)
    frames = []
    for _ in range(3):
        noise = rng.integers(-50, 51, base.shape, dtype=np.int16)
        noisy = np.clip(base.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        frames.append(cv2.cvtColor(noisy, cv2.COLOR_GRAY2BGR))
    frames.append(frame)
    monkeypatch.setattr(
        pipeline,
        "align_reference",
        lambda reference, target, mask: (reference, 999.0, "forced_high_ring"),
    )
    eraser = ClassicalEraser()
    res = eraser.process(frames=frames, subtitle_masks=[np.zeros_like(mask)]*3 + [mask],
                         protected_masks=[np.zeros_like(mask)]*4, scene_ids=[0]*4)
    assert res.reconstruction_sources[3] == "failed_preserved_original"
    assert 3 in res.review_frames


def test_bright_glyph_mask_covers_white_fill_without_flooding():
    from app.workers.runner import _bright_glyph_mask

    frame = np.full((240, 480, 3), (80, 120, 170), np.uint8)
    cv2.putText(frame, "TEXT", (90, 150), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (255, 255, 255), 8)
    mask = _bright_glyph_mask(frame, (70, 80, 340, 100), (90, 95, 250, 65))
    glyph = cv2.inRange(frame, (245, 245, 245), (255, 255, 255)) > 0
    coverage = np.count_nonzero(mask[glyph]) / max(1, np.count_nonzero(glyph))
    assert coverage >= 0.95
    assert np.count_nonzero(mask) / mask.size < 0.15


def test_unknown_subtitle_line_is_erased_but_handle_is_not():
    from app.workers.runner import _is_erase_candidate

    line = {"text_type": "unknown", "review_status": "needs_review", "text": "", "bbox": [120, 847, 320, 60]}
    handle = {"text_type": "unknown", "review_status": "needs_review", "text": "TG@svipktv", "bbox": [397, 848, 251, 175]}
    assert _is_erase_candidate(line, 1280)
    assert not _is_erase_candidate(handle, 1280)


def test_handle_protection_uses_strokes_not_full_bbox():
    from app.workers.runner import _handle_protection_mask

    frame = np.full((240, 480, 3), 60, np.uint8)
    cv2.putText(frame, "TG@svipktv", (130, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (220, 220, 220), 2)
    item = {"text": "TG@svipktv", "bbox": [100, 130, 300, 70]}
    mask = _handle_protection_mask(frame, item)
    assert np.count_nonzero(mask) > 100
    assert np.count_nonzero(mask) < 0.25 * 300 * 70
