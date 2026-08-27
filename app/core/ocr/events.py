from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

import cv2
import numpy as np

from app.core.detection.protocol import TextCandidate
from app.core.detection.tracking import bbox_iou


class ScannerState(str, Enum):
    IDLE = "idle"
    STABLE = "stable"
    TRANSITION = "transition"


@dataclass(frozen=True, slots=True)
class EventScannerConfig:
    idle_scan_fps: float = 2.0
    stable_scan_fps: float = 4.0
    transition_scan_fps: float = 10.0
    same_event_iou: float = 0.35
    missing_grace_frames: int = 2
    stable_after_samples: int = 3
    max_samples_per_event: int = 6

    def __post_init__(self) -> None:
        if min(self.idle_scan_fps, self.stable_scan_fps, self.transition_scan_fps) <= 0:
            raise ValueError("scan FPS values must be positive")
        if not 0.0 <= self.same_event_iou <= 1.0:
            raise ValueError("same_event_iou must be between 0 and 1")
        if self.missing_grace_frames < 0:
            raise ValueError("missing_grace_frames must be non-negative")
        if self.stable_after_samples < 1:
            raise ValueError("stable_after_samples must be at least 1")
        if self.max_samples_per_event < 1:
            raise ValueError("max_samples_per_event must be at least 1")


@dataclass(frozen=True, slots=True)
class EventSample:
    frame_index: int
    frame: np.ndarray
    bbox: tuple[int, int, int, int]
    confidence: float
    sharpness: float
    is_roi: bool = False


@dataclass(frozen=True, slots=True)
class TextEvent:
    id: str
    scene_id: int
    start_frame: int
    end_frame: int
    samples: tuple[EventSample, ...]
    aggregate_bbox: tuple[int, int, int, int]
    stability_confidence: float
    needs_review: bool = False


@dataclass(frozen=True, slots=True)
class EventRecognition:
    event_id: str
    frame_index: int
    results: object


@dataclass(slots=True)
class _ActiveEvent:
    id: str
    scene_id: int
    samples: list[EventSample] = field(default_factory=list)
    last_seen_frame: int = -1
    missing_frames: int = 0

    @property
    def last_bbox(self) -> tuple[int, int, int, int]:
        return self.samples[-1].bbox


class TextEventScanner:
    def __init__(self, config: EventScannerConfig | None = None) -> None:
        self.config = config or EventScannerConfig()
        self.state = ScannerState.IDLE
        self._active: list[_ActiveEvent] = []
        self._last_scene: int | None = None
        self._counter = 0

    @property
    def recommended_scan_fps(self) -> float:
        return {
            ScannerState.IDLE: self.config.idle_scan_fps,
            ScannerState.STABLE: self.config.stable_scan_fps,
            ScannerState.TRANSITION: self.config.transition_scan_fps,
        }[self.state]

    def update(
        self,
        frame: np.ndarray,
        candidates: Sequence[TextCandidate],
        *,
        frame_index: int,
        scene_id: int,
    ) -> list[TextEvent]:
        closed: list[TextEvent] = []
        transitioned = False

        if self._last_scene is not None and scene_id != self._last_scene:
            closed.extend(self._close_all())
            transitioned = True
        self._last_scene = scene_id

        unmatched = set(range(len(candidates)))
        matched_active: set[int] = set()

        for active_index, active in enumerate(list(self._active)):
            if active.scene_id != scene_id or not unmatched:
                continue
            score, candidate_index = max(
                ((bbox_iou(active.last_bbox, candidates[index].bbox), index) for index in unmatched),
                default=(0.0, -1),
            )
            if score >= self.config.same_event_iou:
                self._append_sample(active, frame, candidates[candidate_index], frame_index)
                active.missing_frames = 0
                unmatched.remove(candidate_index)
                matched_active.add(active_index)

        survivors: list[_ActiveEvent] = []
        for index, active in enumerate(self._active):
            if active.scene_id != scene_id:
                closed.append(self._close(active))
                transitioned = True
                continue
            if index not in matched_active:
                active.missing_frames += 1
            if active.missing_frames > self.config.missing_grace_frames:
                closed.append(self._close(active))
                transitioned = True
            else:
                survivors.append(active)
        self._active = survivors

        for candidate_index in sorted(unmatched):
            self._counter += 1
            active = _ActiveEvent(id=f"event-{self._counter:05d}", scene_id=scene_id)
            self._append_sample(active, frame, candidates[candidate_index], frame_index)
            self._active.append(active)
            transitioned = True

        if not self._active:
            self.state = ScannerState.IDLE
        elif transitioned or any(active.missing_frames for active in self._active):
            self.state = ScannerState.TRANSITION
        elif all(len(active.samples) >= self.config.stable_after_samples for active in self._active):
            self.state = ScannerState.STABLE
        else:
            self.state = ScannerState.TRANSITION
        return self._promotable(closed)

    def _promotable(self, events: list[TextEvent]) -> list[TextEvent]:
        # Unstable detections (fewer than stable_after_samples samples) are noise:
        # promoting them floods downstream stages with junk events.
        return [event for event in events if len(event.samples) >= self.config.stable_after_samples]

    def finalize(self) -> list[TextEvent]:
        events = self._promotable(self._close_all())
        self.state = ScannerState.IDLE
        self._last_scene = None
        return events

    def _append_sample(
        self,
        active: _ActiveEvent,
        frame: np.ndarray,
        candidate: TextCandidate,
        frame_index: int,
    ) -> None:
        x, y, w, h = candidate.bbox
        height, width = frame.shape[:2]
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(width, x + w), min(height, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        crop = np.array(frame[y0:y1, x0:x1], copy=True)
        sample = EventSample(
            frame_index=frame_index,
            frame=crop,
            bbox=candidate.bbox,
            confidence=float(candidate.confidence),
            sharpness=_image_sharpness(crop),
            is_roi=True,
        )
        active.last_seen_frame = frame_index
        if len(active.samples) < self.config.max_samples_per_event:
            active.samples.append(sample)
        else:
            # Keep temporal coverage without allowing a long subtitle to grow memory without bound.
            replacement = min(range(len(active.samples)), key=lambda idx: active.samples[idx].sharpness)
            if sample.sharpness > active.samples[replacement].sharpness:
                active.samples[replacement] = sample

    def _close_all(self) -> list[TextEvent]:
        events = [self._close(active) for active in self._active if active.samples]
        self._active.clear()
        return events

    def _close(self, active: _ActiveEvent) -> TextEvent:
        samples = tuple(sorted(active.samples, key=lambda sample: sample.frame_index))
        if not samples:
            raise ValueError("cannot close an event without samples")
        confidence = float(sum(sample.confidence for sample in samples) / len(samples))
        return TextEvent(
            id=active.id,
            scene_id=active.scene_id,
            start_frame=samples[0].frame_index,
            end_frame=samples[-1].frame_index,
            samples=samples,
            aggregate_bbox=_union_bboxes([sample.bbox for sample in samples]),
            stability_confidence=confidence,
            needs_review=confidence < 0.5 or len(samples) < self.config.stable_after_samples,
        )


def _image_sharpness(image: np.ndarray) -> float:
    if image.size == 0:
        return 0.0
    gray = image
    if gray.ndim == 3:
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _region_sharpness(frame: np.ndarray, bbox: tuple[int, int, int, int]) -> float:
    x, y, w, h = bbox
    height, width = frame.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(width, x + w), min(height, y + h)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return _image_sharpness(frame[y0:y1, x0:x1])


def _union_bboxes(boxes: Sequence[tuple[int, int, int, int]]) -> tuple[int, int, int, int]:
    if not boxes:
        raise ValueError("at least one bounding box is required")
    left = min(x for x, _y, _w, _h in boxes)
    top = min(y for _x, y, _w, _h in boxes)
    right = max(x + w for x, _y, w, _h in boxes)
    bottom = max(y + h for _x, y, _w, h in boxes)
    return left, top, right - left, bottom - top


def select_representative_sample(event: TextEvent) -> EventSample:
    if not event.samples:
        raise ValueError("event has no samples")
    sharpness_values = [sample.sharpness for sample in event.samples]
    max_sharpness = max(sharpness_values) or 1.0
    return max(
        event.samples,
        key=lambda sample: 0.35 * sample.confidence + 0.65 * min(1.0, sample.sharpness / max_sharpness),
    )


def fuse_event_ink(event: TextEvent) -> np.ndarray:
    if not event.samples:
        raise ValueError("event has no samples")
    shapes = {sample.frame.shape for sample in event.samples}
    if len(shapes) != 1:
        return np.array(select_representative_sample(event).frame, copy=True)
    stack = np.stack([sample.frame.astype(np.float32) for sample in event.samples], axis=0)
    return np.median(stack, axis=0).astype(np.uint8)


def recognize_text_events(events: Sequence[TextEvent], provider) -> list[EventRecognition]:
    recognized: list[EventRecognition] = []
    for event in events:
        representative = select_representative_sample(event)
        image = fuse_event_ink(event) if len(event.samples) >= 3 else representative.frame
        region = (0, 0, int(image.shape[1]), int(image.shape[0])) if representative.is_roi else event.aggregate_bbox
        results = provider.recognize(
            image,
            [region],
            frame_index=representative.frame_index,
        )
        recognized.append(EventRecognition(event.id, representative.frame_index, results))
    return recognized


def _bbox_area(bbox: tuple[int, int, int, int]) -> int:
    return max(0, bbox[2]) * max(0, bbox[3])


def _inter_area(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    ix = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    iy = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return max(0, ix) * max(0, iy)


def _events_sample_proximate(a: TextEvent, b: TextEvent, max_gap_frames: int) -> bool:
    for sa in a.samples:
        for sb in b.samples:
            if abs(sa.frame_index - sb.frame_index) <= max_gap_frames:
                return True
    return False


def _samples_same_line(
    a: TextEvent,
    b: TextEvent,
    iou_threshold: float,
    containment_threshold: float,
) -> bool:
    for sa in a.samples:
        for sb in b.samples:
            inter = _inter_area(sa.bbox, sb.bbox)
            if inter <= 0:
                continue
            smaller = min(_bbox_area(sa.bbox), _bbox_area(sb.bbox))
            larger = max(_bbox_area(sa.bbox), _bbox_area(sb.bbox))
            containment = inter / smaller if smaller else 0.0
            size_ratio = smaller / larger if larger else 1.0
            overlap_ratio = bbox_iou(sa.bbox, sb.bbox)
            # A line re-detected as smaller partial crops has high
            # containment with a small size ratio. A drifted box of the same
            # line shows mid-range IoU. Two distinct lines occupy nearly
            # identical full-size boxes (ratio ~1, IoU ~1) and must stay
            # separate.
            fragment = containment >= containment_threshold and size_ratio <= 0.85
            drift = iou_threshold <= overlap_ratio < 0.95
            if fragment or drift:
                return True
    return False


def merge_fragmented_events(
    events: Sequence[TextEvent],
    *,
    max_gap_frames: int = 24,
    iou_threshold: float = 0.30,
    containment_threshold: float = 0.80,
    max_samples_per_event: int = 6,
) -> list[TextEvent]:
    """Recombine events that belong to the same on-screen text line.

    Tracking can drop and re-open an event while one subtitle line is still
    visible (motion shifts the box, a detector hiccup exceeds the grace
    window). The fragments OCR to partial text and translate to garbage.
    Events in the same scene that are temporally adjacent and spatially
    overlapping are merged; samples fully contained in a larger crop of the
    same line are dropped so OCR sees the complete line.
    """
    groups: dict[int, list[int]] = {}
    for index, event in enumerate(events):
        groups.setdefault(event.scene_id, []).append(index)

    parent = list(range(len(events)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for scene_indices in groups.values():
        ordered = sorted(scene_indices, key=lambda i: events[i].start_frame)
        for a in range(len(ordered)):
            for b in range(a + 1, len(ordered)):
                ea, eb = events[ordered[a]], events[ordered[b]]
                if not _events_sample_proximate(ea, eb, max_gap_frames):
                    continue
                # Compare actual per-frame sample boxes: aggregate unions can
                # be inflated by drifted samples and falsely overlap other
                # lines (e.g. a tall watermark band swallowing a dialogue).
                if not _samples_same_line(ea, eb, iou_threshold, containment_threshold):
                    continue
                union(ordered[a], ordered[b])

    clusters: dict[int, list[int]] = {}
    for index in range(len(events)):
        clusters.setdefault(find(index), []).append(index)

    merged: list[TextEvent] = []
    for indices in clusters.values():
        if len(indices) == 1:
            merged.append(events[indices[0]])
            continue
        parts = [events[i] for i in indices]
        pool = [sample for event in parts for sample in event.samples]
        kept: list[EventSample] = []
        for sample in sorted(pool, key=lambda s: _bbox_area(s.bbox), reverse=True):
            contained = False
            for keeper in kept:
                area = _bbox_area(sample.bbox)
                if area and _inter_area(keeper.bbox, sample.bbox) / area >= 0.80:
                    contained = True
                    break
            if not contained:
                kept.append(sample)
        kept = sorted(kept, key=lambda s: s.sharpness, reverse=True)[:max_samples_per_event]
        if not kept:
            kept = sorted(pool, key=lambda s: s.sharpness, reverse=True)[:1]
        left, top = min(s.bbox[0] for s in kept), min(s.bbox[1] for s in kept)
        right = max(s.bbox[0] + s.bbox[2] for s in kept)
        bottom = max(s.bbox[1] + s.bbox[3] for s in kept)
        merged.append(TextEvent(
            id=parts[0].id,
            scene_id=parts[0].scene_id,
            start_frame=min(p.start_frame for p in parts),
            end_frame=max(p.end_frame for p in parts),
            samples=tuple(sorted(kept, key=lambda s: s.frame_index)),
            aggregate_bbox=(left, top, right - left, bottom - top),
            stability_confidence=max(p.stability_confidence for p in parts),
            needs_review=any(p.needs_review for p in parts),
        ))
    merged.sort(key=lambda e: e.start_frame)
    return merged
