from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class ProtectedMaskDecision:
    eraser_mask: np.ndarray
    overlap_ratio: float
    needs_review: bool


def estimate_stroke_width(mask: np.ndarray) -> float:
    hard = (mask > 0).astype(np.uint8)
    if not np.any(hard):
        return 1.0
    distance = cv2.distanceTransform(hard, cv2.DIST_L2, 3)
    values = distance[hard > 0]
    return max(1.0, 2.0 * float(np.median(values)))


def adaptive_dilate(mask: np.ndarray, frame_height: int) -> np.ndarray:
    stroke_width = estimate_stroke_width(mask)
    radius = int(round(max(1.0, min(frame_height * 0.006, stroke_width * 0.55))))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (radius * 2 + 1, radius * 2 + 1))
    return cv2.dilate((mask > 0).astype(np.uint8) * 255, kernel)


def subtract_protected_regions(
    subtitle_mask: np.ndarray,
    protected_mask: np.ndarray,
    *,
    max_protected_overlap: float = 0.12,
    protection_margin: int = 2,
) -> ProtectedMaskDecision:
    subtitle = subtitle_mask > 0
    protected = (protected_mask > 0).astype(np.uint8) * 255
    if protection_margin > 0 and np.any(protected):
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (protection_margin * 2 + 1, protection_margin * 2 + 1),
        )
        protected = cv2.dilate(protected, kernel)
    protected_bool = protected > 0
    subtitle_pixels = int(np.count_nonzero(subtitle))
    overlap = int(np.count_nonzero(subtitle & protected_bool))
    ratio = float(overlap / subtitle_pixels) if subtitle_pixels else 0.0
    if ratio > max_protected_overlap:
        return ProtectedMaskDecision(np.zeros_like(subtitle_mask, dtype=np.uint8), ratio, True)
    eraser = subtitle & ~protected_bool
    return ProtectedMaskDecision(eraser.astype(np.uint8) * 255, ratio, False)
