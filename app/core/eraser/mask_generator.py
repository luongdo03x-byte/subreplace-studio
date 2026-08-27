from __future__ import annotations

import cv2
import numpy as np

from .mask_refiner import adaptive_dilate


def _polarity_cluster_mask(roi_gray: np.ndarray, cap: float) -> np.ndarray:
    """Stroke-shaped mask from the glyph luminance cluster.

    Picks the extreme-luminance side (bright or dark) whose mean is farthest
    from the ROI median, solidifies strokes with morphology, and returns
    zeros when the cluster would flood the ROI (no usable text cluster).
    """
    median = float(np.median(roi_gray))
    hi_p = float(np.percentile(roi_gray, 92))
    lo_p = float(np.percentile(roi_gray, 8))
    bright = (roi_gray >= hi_p).astype(np.uint8) * 255
    dark = (roi_gray <= lo_p).astype(np.uint8) * 255
    bright_mean = float(roi_gray[bright > 0].mean()) if np.any(bright) else median
    dark_mean = float(roi_gray[dark > 0].mean()) if np.any(dark) else median
    mask = bright if abs(bright_mean - median) >= abs(dark_mean - median) else dark
    if np.count_nonzero(mask) / max(1, roi_gray.size) > cap:
        return np.zeros_like(mask)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    return mask


def _otsu_glyph_mask(roi_gray: np.ndarray) -> np.ndarray:
    otsu_t, bright = cv2.threshold(roi_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    del otsu_t
    median = float(np.median(roi_gray))
    bright_mean = float(roi_gray[bright > 0].mean()) if np.any(bright) else median
    dark = (bright == 0).astype(np.uint8) * 255
    dark_mean = float(roi_gray[dark > 0].mean()) if np.any(dark) else median
    mask = bright if abs(bright_mean - median) >= abs(dark_mean - median) else dark
    area = roi_gray.size
    if not area or np.count_nonzero(mask) / area > 0.45:
        return np.zeros_like(mask)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    return mask


def _mask_from_gray(gray: np.ndarray) -> np.ndarray:
    lo, hi = np.percentile(gray, [18, 82])
    if hi - lo < 8:
        # Flat ROI: the percentile gates degenerate (lo == hi) and the
        # legacy mask would flood the whole region.
        return _otsu_glyph_mask(gray)
    # Difference-of-Gaussians: glyph strokes are strong positive
    # excursions against their immediate surroundings on any background,
    # while low-amplitude texture and noise stay below the adaptive gate.
    blur = cv2.GaussianBlur(gray, (0, 0), 9)
    dog = gray.astype(np.float32) - blur.astype(np.float32)
    gate = max(14.0, 0.35 * float(np.percentile(dog, 99)))
    mask = ((dog >= gate) * 255).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    # Glyph interiors with soft glow can still fall below the gate;
    # recover them from the luminance cluster when coverage is too thin.
    min_pixels = max(40, int(0.02 * gray.size))
    if np.count_nonzero(mask) < min_pixels:
        fallback = _polarity_cluster_mask(gray, cap=0.35)
        if np.any(fallback):
            mask = fallback
    return mask


def generate_stroke_mask(
    frame: np.ndarray,
    bbox: tuple[int, int, int, int],
    *,
    dilate: bool = True,
) -> np.ndarray:
    x, y, w, h = bbox
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(frame.shape[1], x + w), min(frame.shape[0], y + h)
    result = np.zeros(frame.shape[:2], dtype=np.uint8)
    if x1 <= x0 or y1 <= y0:
        return result
    gray = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    result[y0:y1, x0:x1] = _mask_from_gray(gray)
    return adaptive_dilate(result, frame.shape[0]) if dilate else result


def temporal_stroke_mask(rois: list[np.ndarray], *, dilate: bool = True) -> np.ndarray:
    """Stroke mask for a static text region observed across multiple frames.

    Burned-in subtitles are stationary while the background behind them
    moves (swaying fabric, shimmering beads, camera noise). The per-pixel
    minimum over the event's frames suppresses transient background
    highlights and keeps the static glyph layer, which the single-frame
    gates then segment cleanly. Falls back to the single-frame mask when
    only one frame is available.
    """
    if not rois:
        raise ValueError("temporal_stroke_mask requires at least one ROI")
    reference = rois[0] if isinstance(rois[0], np.ndarray) else np.asarray(rois[0])
    if len(rois) == 1:
        gray = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY) if reference.ndim == 3 else reference
        mask = _mask_from_gray(gray)
        return adaptive_dilate(mask, reference.shape[0] * 8) if dilate else mask
    stack = np.min(np.stack([np.asarray(r, dtype=np.uint8) for r in rois]), axis=0)
    gray = cv2.cvtColor(stack, cv2.COLOR_BGR2GRAY) if stack.ndim == 3 else stack
    mask = _mask_from_gray(gray)
    return adaptive_dilate(mask, reference.shape[0] * 8) if dilate else mask
