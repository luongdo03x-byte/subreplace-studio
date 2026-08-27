from __future__ import annotations

import cv2
import numpy as np

from .style import SubtitleStyle


def _ass_bgr(pixel: np.ndarray) -> str:
    b, g, r = (int(round(value)) for value in pixel[:3])
    return f"&H00{b:02X}{g:02X}{r:02X}"


class StyleAnalyzer:
    def analyze(
        self,
        frame: np.ndarray,
        stroke_mask: np.ndarray,
        *,
        bbox: tuple[int, int, int, int],
    ) -> SubtitleStyle:
        if frame.ndim != 3 or frame.shape[2] < 3:
            raise ValueError("frame must be a BGR image")
        if stroke_mask.shape != frame.shape[:2]:
            raise ValueError("stroke mask shape must match frame")
        x, y, width, height = bbox
        if width <= 0 or height <= 0:
            raise ValueError("bbox must have positive width and height")
        h, w = frame.shape[:2]
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(w, x + width), min(h, y + height)
        roi = frame[y0:y1, x0:x1, :3]
        roi_mask = stroke_mask[y0:y1, x0:x1] > 0
        pixels = roi[roi_mask]
        if pixels.size == 0:
            pixels = roi.reshape(-1, 3)
        if pixels.size == 0:
            return SubtitleStyle(font_size=max(12, round(height * 0.9)))

        gray = cv2.cvtColor(pixels.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_BGR2GRAY).reshape(-1)
        order = np.argsort(gray)
        count = len(order)
        low = pixels[order[: max(1, count // 4)]].mean(axis=0)
        high = pixels[order[max(0, count * 3 // 4) :]].mean(axis=0)
        font_size = max(12, round(height * 0.9))
        outline_width = max(1.0, min(4.0, height * 0.08))
        margin_bottom = max(12, min(round(h * 0.22), h - (y0 + (y1 - y0))))
        max_width_ratio = min(0.94, max(0.65, (width / max(1, w)) * 1.18))
        return SubtitleStyle(
            font_size=font_size,
            fill_color=_ass_bgr(high),
            outline_color=_ass_bgr(low),
            outline_width=outline_width,
            margin_bottom=margin_bottom,
            max_width_ratio=max_width_ratio,
        )
