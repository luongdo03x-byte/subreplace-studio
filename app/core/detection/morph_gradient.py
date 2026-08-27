from __future__ import annotations

import cv2
import numpy as np

from .protocol import TextCandidate


class MorphGradientDetector:
    def __init__(self, *, min_area: int = 40, max_area_fraction: float = 0.20) -> None:
        self.min_area = min_area
        self.max_area_fraction = max_area_fraction

    def detect(self, frame: np.ndarray, frame_index: int) -> list[TextCandidate]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gradient = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
        _, binary = cv2.threshold(gradient, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        # Join characters into text-like horizontal components without cropping the frame.
        joined = cv2.morphologyEx(
            binary,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (9, 3)),
        )
        contours, _ = cv2.findContours(joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        frame_area = frame.shape[0] * frame.shape[1]
        candidates: list[TextCandidate] = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = w * h
            if area < self.min_area or area > frame_area * self.max_area_fraction:
                continue
            if w < h * 0.8:
                continue
            contour_area = max(float(cv2.contourArea(contour)), 1.0)
            confidence = float(min(1.0, contour_area / max(area * 0.35, 1.0)))
            polygon = ((x, y), (x + w, y), (x + w, y + h), (x, y + h))
            candidates.append(TextCandidate((x, y, w, h), polygon, confidence, frame_index))
        candidates.sort(key=lambda item: (item.bbox[1], item.bbox[0]))
        return candidates
