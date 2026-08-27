from __future__ import annotations

from dataclasses import dataclass, field

from app.models.text_track import TextTrack

from .protocol import TextCandidate


def bbox_iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x0, y0 = max(ax, bx), max(ay, by)
    x1, y1 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    intersection = max(0, x1 - x0) * max(0, y1 - y0)
    union = aw * ah + bw * bh - intersection
    return float(intersection / union) if union else 0.0


@dataclass(slots=True)
class _ActiveTrack:
    id: str
    frame_indices: list[int] = field(default_factory=list)
    bboxes: list[tuple[int, int, int, int]] = field(default_factory=list)
    last_frame: int = -1

    def add(self, candidate: TextCandidate) -> None:
        self.frame_indices.append(candidate.frame_index)
        self.bboxes.append(candidate.bbox)
        self.last_frame = candidate.frame_index

    def to_domain(self) -> TextTrack:
        return TextTrack(id=self.id, frame_indices=list(self.frame_indices), bboxes=list(self.bboxes))


class TextTracker:
    def __init__(self, *, iou_threshold: float = 0.30, max_gap: int = 2) -> None:
        self.iou_threshold = iou_threshold
        self.max_gap = max_gap
        self._active: list[_ActiveTrack] = []
        self._finished: list[TextTrack] = []
        self._last_scene: int | None = None
        self._counter = 0

    def _finish_all(self) -> None:
        self._finished.extend(track.to_domain() for track in self._active)
        self._active.clear()

    def update(self, candidates: list[TextCandidate], *, frame_index: int, scene_id: int) -> None:
        if self._last_scene is not None and scene_id != self._last_scene:
            self._finish_all()
        self._last_scene = scene_id
        still_active: list[_ActiveTrack] = []
        for track in self._active:
            if frame_index - track.last_frame <= self.max_gap + 1:
                still_active.append(track)
            else:
                self._finished.append(track.to_domain())
        self._active = still_active

        unmatched = set(range(len(candidates)))
        for track in self._active:
            if not unmatched:
                break
            scored = [
                (bbox_iou(track.bboxes[-1], candidates[i].bbox), i)
                for i in unmatched
            ]
            score, best = max(scored, default=(0.0, -1))
            if score >= self.iou_threshold:
                track.add(candidates[best])
                unmatched.remove(best)
        for index in sorted(unmatched):
            self._counter += 1
            track = _ActiveTrack(id=f"track-{self._counter:05d}")
            track.add(candidates[index])
            self._active.append(track)

    def finalize(self) -> list[TextTrack]:
        self._finish_all()
        return list(self._finished)
