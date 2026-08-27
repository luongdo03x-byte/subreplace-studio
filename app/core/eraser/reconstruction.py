from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np


def median_fusion(candidates: Sequence[np.ndarray]) -> np.ndarray:
    if not candidates:
        raise ValueError("at least one reconstruction candidate is required")
    stack = np.stack(candidates, axis=0).astype(np.float32)
    return np.clip(np.median(stack, axis=0), 0, 255).astype(np.uint8)


def compose_inside_mask(
    original: np.ndarray,
    generated: np.ndarray,
    mask: np.ndarray,
    feather: int = 2,
) -> np.ndarray:
    hard = mask > 0
    if not np.any(hard):
        return original.copy()
    alpha = hard.astype(np.float32)
    if feather > 0:
        alpha = cv2.GaussianBlur(alpha, (0, 0), sigmaX=max(feather / 2.0, 0.1))
    alpha[~hard] = 0.0
    if original.ndim == 3:
        alpha = alpha[..., None]
    blended = original.astype(np.float32) * (1.0 - alpha) + generated.astype(np.float32) * alpha
    result = original.copy()
    if original.ndim == 3:
        result[hard] = np.clip(blended[hard], 0, 255).astype(np.uint8)
    else:
        result[hard] = np.clip(blended[hard], 0, 255).astype(np.uint8)
    return result


def single_frame_inpaint(frame: np.ndarray, mask: np.ndarray) -> np.ndarray:
    hard = (mask > 0).astype(np.uint8) * 255
    if not np.any(hard):
        return frame.copy()
    return cv2.inpaint(frame, hard, 3.0, cv2.INPAINT_NS)
