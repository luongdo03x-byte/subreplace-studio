from __future__ import annotations

import re
import statistics
from typing import Any


_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def _box(item: dict[str, Any]) -> tuple[int, int, int, int]:
    raw = item.get("anchor_bbox") or item.get("bbox") or [0, 0, 0, 0]
    return tuple(int(v) for v in raw) if isinstance(raw, list) and len(raw) == 4 else (0, 0, 0, 0)


def _cjk(value: object) -> str:
    return "".join(_CJK_RE.findall(str(value or "")))


def _related(left: dict[str, Any], right: dict[str, Any]) -> bool:
    overlap = min(int(left.get("end_frame", 0)), int(right.get("end_frame", 0))) - max(
        int(left.get("start_frame", 0)), int(right.get("start_frame", 0))
    ) + 1
    if overlap < 3:
        return False
    left_duration = int(left.get("end_frame", 0)) - int(left.get("start_frame", 0)) + 1
    right_duration = int(right.get("end_frame", 0)) - int(right.get("start_frame", 0)) + 1
    if overlap / max(1, min(left_duration, right_duration)) < 0.25:
        return False
    lx, ly, lw, lh = _box(left)
    rx, ry, rw, rh = _box(right)
    left_center = lx + lw / 2.0
    right_center = rx + rw / 2.0
    same_band = abs((ly + lh) - (ry + rh)) <= max(48, 1.5 * max(lh, rh))
    separated = abs(left_center - right_center) >= max(24, 0.8 * max(lh, rh))
    same_timing = (
        int(left.get("start_frame", 0)) == int(right.get("start_frame", 0))
        and int(left.get("end_frame", 0)) == int(right.get("end_frame", 0))
    )
    short_fragment = min(len(_cjk(left.get("text"))), len(_cjk(right.get("text")))) <= 2
    return bool(same_band and (separated or same_timing or short_fragment))


def _drop_isolated_singleton(
    item: dict[str, Any], dialogue: list[dict[str, Any]], baseline: float
) -> bool:
    if len(_cjk(item.get("text"))) != 1:
        return False
    if any(
        other is not item
        and len(_cjk(other.get("text"))) >= 2
        and _related(item, other)
        for other in dialogue
    ):
        return False
    _, y, _, h = _box(item)
    duration = int(item.get("end_frame", 0)) - int(item.get("start_frame", 0)) + 1
    return abs((y + h) - baseline) > 120 or duration < 10


def _merge(cluster: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(cluster, key=lambda item: (_box(item)[0], int(item.get("start_frame", 0))))
    unique: list[dict[str, Any]] = []
    for item in ordered:
        text = _cjk(item.get("text"))
        if any(text and text in _cjk(other.get("text")) for other in ordered if other is not item):
            continue
        unique.append(item)
    if not unique:
        unique = [max(ordered, key=lambda item: len(_cjk(item.get("text"))))]
    boxes = [_box(item) for item in unique]
    x0 = min(box[0] for box in boxes); y0 = min(box[1] for box in boxes)
    x1 = max(box[0] + box[2] for box in boxes); y1 = max(box[1] + box[3] for box in boxes)
    merged = dict(unique[0])
    merged.update({
        "event_id": "+".join(str(item.get("event_id") or "") for item in unique),
        "start_frame": min(int(item.get("start_frame", 0)) for item in unique),
        "end_frame": max(int(item.get("end_frame", 0)) for item in unique),
        "text": "".join(str(item.get("text") or "").strip() for item in unique),
        "confidence": min(float(item.get("confidence", 0.0)) for item in unique),
        "bbox": [x0, y0, x1 - x0, y1 - y0],
        "anchor_bbox": [x0, y0, x1 - x0, y1 - y0],
        "fragment_ids": [str(item.get("event_id") or "") for item in unique],
    })
    return merged


def coalesce_dialogue_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dialogue = [
        dict(item) for item in events
        if str(item.get("text_type")) == "dialogue_subtitle"
        and str(item.get("review_status")) in {"auto", "approved"}
        and str(item.get("text") or "").strip()
    ]
    phrase_baselines = [
        y + h for item in dialogue if len(_cjk(item.get("text"))) >= 2
        for _, y, _, h in [_box(item)]
    ]
    if phrase_baselines:
        baseline = float(statistics.median(phrase_baselines))
        dialogue = [
            item for item in dialogue
            if not _drop_isolated_singleton(item, dialogue, baseline)
        ]
    dialogue.sort(key=lambda item: (int(item.get("start_frame", 0)), _box(item)[0]))
    clusters: list[list[dict[str, Any]]] = []
    for item in dialogue:
        if clusters and any(_related(existing, item) for existing in clusters[-1]):
            clusters[-1].append(item)
        else:
            clusters.append([item])
    merged = [_merge(cluster) if len(cluster) > 1 else cluster[0] for cluster in clusters]
    result: list[dict[str, Any]] = []
    for item in merged:
        if (
            result
            and _cjk(result[-1].get("text")) == _cjk(item.get("text"))
            and int(item.get("start_frame", 0)) - int(result[-1].get("end_frame", 0)) <= 12
        ):
            result[-1]["end_frame"] = max(
                int(result[-1].get("end_frame", 0)), int(item.get("end_frame", 0))
            )
            continue
        result.append(item)
    return result
