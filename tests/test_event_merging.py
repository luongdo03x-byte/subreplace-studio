"""One subtitle line must not fragment into multiple events.

On test_60s.mp4 the line 我不是在三角洲 (f423-480) was detected as 5
overlapping events (我不是在三角洲/是在三/我不/角洲/肉). Each fragment was
OCR'd and translated independently -> duplicated garbage SRT entries at
00:00:17. merge_fragmented_events must recombine them.
"""
import numpy as np

from app.core.detection.protocol import TextCandidate
from app.core.ocr.events import (
    EventSample,
    EventScannerConfig,
    TextEvent,
    TextEventScanner,
    merge_fragmented_events,
)


def _sample(frame_index, bbox, conf=0.95, sharpness=100.0):
    x, y, w, h = bbox
    return EventSample(
        frame_index=frame_index,
        frame=np.full((h, w, 3), 128, dtype=np.uint8),
        bbox=bbox,
        confidence=conf,
        sharpness=sharpness,
        is_roi=True,
    )


def _event(eid, start, end, bbox, samples=None):
    return TextEvent(
        id=eid, scene_id=1, start_frame=start, end_frame=end,
        samples=tuple(samples or [_sample(start, bbox)]),
        aggregate_bbox=bbox, stability_confidence=0.95,
    )


def test_temporal_spatial_overlap_merges():
    full = _event("e1", 423, 435, (150, 940, 420, 60))
    frag = _event("e2", 438, 459, (160, 942, 300, 55))
    merged = merge_fragmented_events([full, frag])
    assert len(merged) == 1
    m = merged[0]
    assert m.start_frame == 423 and m.end_frame == 459
    assert m.aggregate_bbox == (150, 940, 420, 60)


def test_contained_fragment_samples_dropped():
    full_sample = _sample(424, (150, 940, 420, 60), sharpness=120.0)
    frag_sample = _sample(440, (160, 942, 300, 55), sharpness=300.0)
    full = _event("e1", 423, 435, (150, 940, 420, 60), [full_sample])
    frag = _event("e2", 438, 459, (160, 942, 300, 55), [frag_sample])
    merged = merge_fragmented_events([full, frag])
    assert len(merged) == 1
    assert len(merged[0].samples) == 1
    assert merged[0].samples[0].bbox == (150, 940, 420, 60), \
        "full-line crop must survive, contained fragment crop must be dropped"


def test_different_scenes_not_merged():
    a = TextEvent(id="a", scene_id=1, start_frame=10, end_frame=20,
                  samples=(_sample(10, (100, 900, 200, 50)),),
                  aggregate_bbox=(100, 900, 200, 50), stability_confidence=0.9)
    b = TextEvent(id="b", scene_id=2, start_frame=12, end_frame=22,
                  samples=(_sample(12, (100, 900, 200, 50)),),
                  aggregate_bbox=(100, 900, 200, 50), stability_confidence=0.9)
    assert len(merge_fragmented_events([a, b])) == 2


def test_distant_events_not_merged():
    a = _event("a", 100, 120, (300, 850, 200, 50))
    b = _event("b", 400, 420, (300, 850, 200, 50))
    assert len(merge_fragmented_events([a, b])) == 2


def test_scanner_output_end_to_end_merge():
    scanner = TextEventScanner(EventScannerConfig())
    frame = np.zeros((1280, 720, 3), dtype=np.uint8)
    closed = []
    for i in (0, 5, 10):
        closed += scanner.update(frame, [_candidate := TextCandidate(
            bbox=(300, 900, 200, 60), polygon=((300, 900), (500, 900), (500, 960), (300, 960)),
            confidence=0.9, frame_index=i)], frame_index=i, scene_id=0)
    for i in (25, 30, 35):
        closed += scanner.update(frame, [TextCandidate(
            bbox=(310, 905, 190, 55), polygon=((310, 905), (500, 905), (500, 960), (310, 960)),
            confidence=0.9, frame_index=i)], frame_index=i, scene_id=0)
    closed += scanner.finalize()
    merged = merge_fragmented_events(closed)
    assert len(merged) == 1, f"expected single merged event, got {len(merged)}"


def test_consecutive_different_lines_same_position_not_merged():
    a = _event("a", 100, 140, (300, 850, 200, 50))
    b = _event("b", 145, 180, (302, 851, 198, 49))
    assert len(merge_fragmented_events([a, b])) == 2


def test_inflated_neighbor_event_must_not_swallow_dialogue():
    """Aggregate bbox of a drifted watermark band overlaps a dialogue box,
    but their actual samples never overlap spatially -> no merge."""
    wm = TextEvent(
        id="wm", scene_id=1, start_frame=150, end_frame=174,
        samples=(
            _sample(153, (213, 656, 395, 230)),
            _sample(162, (220, 660, 390, 225)),
        ),
        aggregate_bbox=(213, 656, 395, 230), stability_confidence=0.95,
    )
    dlg = TextEvent(
        id="dlg", scene_id=1, start_frame=162, end_frame=174,
        samples=(
            _sample(163, (302, 846, 115, 59)),
            _sample(168, (301, 847, 116, 58)),
        ),
        aggregate_bbox=(302, 846, 115, 59), stability_confidence=1.0,
    )
    merged = merge_fragmented_events([wm, dlg])
    assert len(merged) == 2, "sample-level disjoint boxes must not merge"
