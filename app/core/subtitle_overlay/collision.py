from dataclasses import dataclass


@dataclass(frozen=True)
class Collision:
    timestamp_ms: int
    bbox: tuple[int, int, int, int]


@dataclass(frozen=True)
class CollisionReport:
    collisions: tuple[Collision, ...]
    complete: bool
    checked_frames: int


def check_collisions(frames, detector, cues, layout, line_height, source_width, cancel_event=None):
    collisions = []
    checked = 0
    cue_index = 0
    for frame in frames:
        if cancel_event is not None and cancel_event.is_set():
            return CollisionReport(tuple(collisions), False, checked)
        checked += 1
        while cue_index < len(cues) and cues[cue_index].end_ms <= frame.timestamp_ms:
            cue_index += 1
        if cue_index == len(cues) or frame.timestamp_ms < cues[cue_index].start_ms:
            continue
        # Full-width reservation is conservative and includes horizontal outlines.
        top = max(0, layout.y - 4)
        bottom = layout.y + len(cues[cue_index].lines) * line_height
        for candidate in detector.detect(frame.image, frame.index):
            x, y, w, h = candidate.bbox
            if x < source_width and x+w > 0 and y < bottom and y+h > top:
                collisions.append(Collision(frame.timestamp_ms, candidate.bbox))
                break
    return CollisionReport(tuple(collisions), checked > 0, checked)
