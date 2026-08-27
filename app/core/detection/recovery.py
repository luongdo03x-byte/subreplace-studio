from __future__ import annotations

from collections.abc import Callable
import re
from typing import Any

import cv2
import numpy as np


_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def subtitle_band(events: list[dict[str, Any]], frame_height: int) -> tuple[int, int]:
    boxes = []
    for item in events:
        if str(item.get("text_type")) != "dialogue_subtitle":
            continue
        raw = item.get("anchor_bbox") or item.get("bbox")
        if isinstance(raw, list) and len(raw) == 4 and int(raw[3]) > 0:
            boxes.append(tuple(int(v) for v in raw))
    if not boxes:
        return int(round(frame_height * 0.64)), max(24, int(round(frame_height * 0.10)))
    tops = np.array([box[1] for box in boxes], dtype=np.float64)
    bottoms = np.array([box[1] + box[3] for box in boxes], dtype=np.float64)
    top = max(0, int(round(float(np.percentile(tops, 20)) - frame_height * 0.012)))
    bottom = min(frame_height, int(round(float(np.percentile(bottoms, 80)) + frame_height * 0.012)))
    return top, max(24, bottom - top)


def subtitle_candidate_mask(frame: np.ndarray, band: tuple[int, int]) -> np.ndarray:
    y, h = band
    roi = frame[max(0, y):min(frame.shape[0], y + h)]
    result = np.zeros(frame.shape[:2], np.uint8)
    if roi.size == 0:
        return result
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    raw = ((hsv[:, :, 1] < 60) & (hsv[:, :, 2] > 180)).astype(np.uint8) * 255
    raw = cv2.morphologyEx(raw, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(raw)
    kept = np.zeros_like(raw)
    for label in range(1, count):
        _, _, width, height, area = stats[label]
        if 3 <= area and width <= max(48, frame.shape[1] // 8) and height <= max(24, h * 9 // 10):
            kept[labels == label] = 255
    result[max(0, y):max(0, y) + kept.shape[0]] = kept
    return result


def is_subtitle_candidate(mask: np.ndarray, band: tuple[int, int]) -> bool:
    y, h = band
    ys, xs = np.where(mask[max(0, y):max(0, y) + h] > 0)
    if len(xs) < max(80, int(mask.shape[1] * h * 0.003)):
        return False
    return int(xs.max() - xs.min() + 1) >= int(mask.shape[1] * 0.08)


def mask_similarity(left: np.ndarray, right: np.ndarray) -> float:
    left_small = cv2.resize(left, (180, 32), interpolation=cv2.INTER_AREA) > 32
    right_small = cv2.resize(right, (180, 32), interpolation=cv2.INTER_AREA) > 32
    union = np.count_nonzero(left_small | right_small)
    return float(np.count_nonzero(left_small & right_small) / union) if union else 0.0


def _normalized_text(value: str) -> str:
    return "".join(_CJK_RE.findall(value))


def recover_missing_events(
    video_path: str,
    events: list[dict[str, Any]],
    recognize: Callable[[np.ndarray, list[tuple[int, int, int, int]], int], tuple[str, float]],
) -> list[dict[str, Any]]:
    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise ValueError(f"cannot decode video: {video_path}")
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if frame_count <= 0 or width <= 0 or height <= 0:
        capture.release()
        raise ValueError("video metadata is invalid for subtitle recovery")

    band = subtitle_band(events, height)
    occupied = np.zeros(frame_count, dtype=np.bool_)
    for item in events:
        if str(item.get("text_type")) != "dialogue_subtitle":
            continue
        start = max(0, int(item.get("start_frame", 0)))
        end = min(frame_count - 1, int(item.get("end_frame", -1)))
        if end >= start:
            occupied[start:end + 1] = True

    intervals: list[tuple[int, int, np.ndarray]] = []
    start: int | None = None
    previous_mask: np.ndarray | None = None
    representative: np.ndarray | None = None
    last_frame = -1
    try:
        for index in range(frame_count):
            ok, frame = capture.read()
            if not ok:
                break
            mask = subtitle_candidate_mask(frame, band)
            active = not occupied[index] and is_subtitle_candidate(mask, band)
            changed = previous_mask is not None and mask_similarity(previous_mask, mask) < 0.68
            if active and (start is None or not changed):
                if start is None:
                    start = index
                representative = frame.copy()
                previous_mask = mask
                last_frame = index
                continue
            if start is not None and last_frame - start + 1 >= 3 and representative is not None:
                intervals.append((start, last_frame, representative))
            start = index if active else None
            previous_mask = mask if active else None
            representative = frame.copy() if active else None
            last_frame = index if active else -1
        if start is not None and last_frame - start + 1 >= 3 and representative is not None:
            intervals.append((start, last_frame, representative))
    finally:
        capture.release()

    recovered = [dict(item) for item in events]
    y, h = band
    for start, end, frame in intervals:
        text, confidence = recognize(frame, [(0, y, width, h)], end)
        normalized = _normalized_text(text)
        if len(normalized) < 2 or confidence < 0.35:
            continue
        previous = max(
            (
                item for item in recovered
                if str(item.get("text_type")) == "dialogue_subtitle"
                and int(item.get("end_frame", -99)) < start
            ),
            key=lambda item: int(item.get("end_frame", -99)),
            default=None,
        )
        if (
            previous is not None
            and start - int(previous.get("end_frame", -99)) <= 12
            and _normalized_text(str(previous.get("text") or "")) == normalized
        ):
            previous["end_frame"] = end
            continue
        mask = subtitle_candidate_mask(frame, band)
        points = cv2.findNonZero(mask)
        anchor = list(cv2.boundingRect(points)) if points is not None else [0, y, width, h]
        recovered.append({
            "event_id": f"event-recovered-{start:06d}",
            "start_frame": start,
            "end_frame": end,
            "frame_index": end,
            "text": text,
            "confidence": float(confidence),
            "bbox": [0, y, width, h],
            "anchor_bbox": anchor,
            "samples": [{"frame_index": end, "bbox": anchor}],
            "text_type": "dialogue_subtitle",
            "review_status": "auto",
            "classification_confidence": float(confidence),
            "classification_margin": float(confidence),
            "speech_overlap": 0.0,
            "recovered": True,
        })
    recovered.sort(key=lambda item: (int(item.get("start_frame", 0)), str(item.get("event_id") or "")))
    return recovered
