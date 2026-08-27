from __future__ import annotations

import cv2
import numpy as np


def ring_mask(mask: np.ndarray, radius: int = 5) -> np.ndarray:
    hard = (mask > 0).astype(np.uint8) * 255
    if not np.any(hard):
        return hard
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (radius * 2 + 1, radius * 2 + 1))
    dilated = cv2.dilate(hard, kernel)
    return cv2.subtract(dilated, hard)


def ring_mae(reference: np.ndarray, target: np.ndarray, mask: np.ndarray) -> float:
    ring = ring_mask(mask)
    hard = ring > 0
    if not np.any(hard):
        return 0.0
    diff = np.abs(reference.astype(np.float32) - target.astype(np.float32))
    return float(diff[hard].mean())


def ring_mae_robust(reference: np.ndarray, target: np.ndarray, mask: np.ndarray) -> float:
    """Shimmer-robust ring error using the per-pixel-difference median.

    Raw ring MAE conflates stochastic background sparkle (bead curtains,
    fabric shimmer) with alignment error: a small fraction of wildly
    differing pixels dominates the mean, rejecting perfect reconstructions
    on textured scenes. The median over the ring is insensitive to that
    sparse outlier population while genuine misalignment shifts most ring
    pixels and still fails. Gate thresholds are unchanged.
    """
    ring = ring_mask(mask)
    hard = ring > 0
    if not np.any(hard):
        return 0.0
    diff = np.abs(reference.astype(np.float32) - target.astype(np.float32)).mean(axis=2)
    return float(np.median(diff[hard]))


def flicker_ratio(
    current: np.ndarray,
    previous: np.ndarray,
    mask: np.ndarray,
    radius: int = 5,
) -> float:
    region = mask > 0
    ring = ring_mask(mask, radius) > 0
    diff = np.abs(current.astype(np.float32) - previous.astype(np.float32)).mean(axis=2)
    region_change = float(diff[region].mean()) if np.any(region) else 0.0
    ring_change = float(diff[ring].mean()) if np.any(ring) else 0.0
    return region_change / max(ring_change, 1.0)
