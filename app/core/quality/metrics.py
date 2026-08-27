from __future__ import annotations

import math
from collections.abc import Sequence

import cv2
import numpy as np


def _bool_mask(mask: np.ndarray) -> np.ndarray:
    if mask.ndim != 2:
        raise ValueError("mask must be HxW")
    return mask > 0


def outside_mask_changed_pixels(
    original: np.ndarray, result: np.ndarray, mask: np.ndarray
) -> int:
    if original.shape != result.shape:
        raise ValueError("original and result must have identical shape")
    hard = _bool_mask(mask)
    changed = np.any(original != result, axis=2) if original.ndim == 3 else original != result
    return int(np.count_nonzero(changed & ~hard))


def mean_absolute_error(
    expected: np.ndarray, actual: np.ndarray, mask: np.ndarray | None = None
) -> float:
    diff = np.abs(expected.astype(np.float32) - actual.astype(np.float32))
    if mask is None:
        return float(diff.mean())
    hard = _bool_mask(mask)
    if not np.any(hard):
        return 0.0
    return float(diff[hard].mean())


def masked_psnr(expected: np.ndarray, actual: np.ndarray, mask: np.ndarray) -> float:
    hard = _bool_mask(mask)
    if not np.any(hard):
        return float("inf")
    delta = expected.astype(np.float32)[hard] - actual.astype(np.float32)[hard]
    mse = float(np.mean(delta * delta))
    if mse == 0.0:
        return float("inf")
    return float(10.0 * math.log10((255.0 * 255.0) / mse))


def uniform_rectangle_score(
    image: np.ndarray, mask: np.ndarray, *, expected: np.ndarray | None = None
) -> float:
    hard = _bool_mask(mask)
    if not np.any(hard):
        return 0.0
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    ys, xs = np.nonzero(hard)
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    roi = gray[y0:y1, x0:x1].astype(np.float32)
    if expected is not None:
        expected_gray = (
            cv2.cvtColor(expected, cv2.COLOR_BGR2GRAY) if expected.ndim == 3 else expected
        )
        expected_roi = expected_gray[y0:y1, x0:x1].astype(np.float32)
        expected_var = float(np.var(expected_roi))
        actual_var = float(np.var(roi))
        if expected_var <= 1e-6:
            return 0.0 if actual_var <= 1e-6 else 0.0
        # A solid/blurred cover collapses local variance compared with clean ground truth.
        return float(np.clip(1.0 - actual_var / expected_var, 0.0, 1.0))
    masked_values = gray[hard].astype(np.float32)
    roi_var = float(np.var(roi)) + 1e-6
    masked_var = float(np.var(masked_values))
    return float(np.clip(1.0 - (masked_var / roi_var), 0.0, 1.0))


def residual_text_energy(
    source_with_text: np.ndarray,
    reconstructed: np.ndarray,
    clean_reference: np.ndarray,
    mask: np.ndarray,
) -> float:
    hard = _bool_mask(mask)
    if not np.any(hard):
        return 0.0

    def edge(im: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY) if im.ndim == 3 else im
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        return cv2.magnitude(gx, gy)

    source_delta = np.abs(edge(source_with_text) - edge(clean_reference))[hard]
    result_delta = np.abs(edge(reconstructed) - edge(clean_reference))[hard]
    denom = float(np.mean(source_delta)) + 1e-6
    return float(np.clip(float(np.mean(result_delta)) / denom, 0.0, 10.0))


def temporal_flicker(
    frames: Sequence[np.ndarray], masks: Sequence[np.ndarray], ring_masks: Sequence[np.ndarray]
) -> float:
    if len(frames) < 2:
        return 0.0
    values: list[float] = []
    for i in range(1, len(frames)):
        region = _bool_mask(masks[i] | masks[i - 1])
        ring = _bool_mask(ring_masks[i] | ring_masks[i - 1])
        diff = np.abs(frames[i].astype(np.float32) - frames[i - 1].astype(np.float32))
        if diff.ndim == 3:
            diff = diff.mean(axis=2)
        region_change = float(diff[region].mean()) if np.any(region) else 0.0
        ring_change = float(diff[ring].mean()) if np.any(ring) else 0.0
        values.append(region_change / max(ring_change, 1.0))
    return float(np.percentile(np.asarray(values, dtype=np.float32), 90))


def aggregate_psnr(
    expected_frames: Sequence[np.ndarray],
    actual_frames: Sequence[np.ndarray],
    masks: Sequence[np.ndarray],
) -> tuple[float, float]:
    values = [
        masked_psnr(expected, actual, mask)
        for expected, actual, mask in zip(expected_frames, actual_frames, masks, strict=True)
        if np.any(mask)
    ]
    if not values:
        return float("inf"), float("inf")
    finite = [v for v in values if math.isfinite(v)]
    if not finite:
        return float("inf"), float("inf")
    return float(np.mean(finite)), float(np.min(finite))
