"""Protection rects must track per-frame sample locations.

event-02534 (TG@svipktv, frames 153-171) had aggregate bbox [213,656,395,230]
while true text is ~216x44. Filling the aggregate rect blocked dialogue
erasure via protected_collision on frames 162-171.
"""
from app.workers.runner import protected_bbox_for_frame


ITEM = {
    "bbox": [213, 656, 395, 230],
    "samples": [
        {"frame_index": 153, "bbox": [300, 660, 220, 46]},
        {"frame_index": 162, "bbox": [296, 664, 222, 44]},
        {"frame_index": 170, "bbox": [290, 668, 224, 45]},
    ],
}


def test_exact_sample_frame():
    assert protected_bbox_for_frame(ITEM, 162) == (296, 664, 222, 44)


def test_nearest_sample_between_frames():
    assert protected_bbox_for_frame(ITEM, 165) == (296, 664, 222, 44)
    assert protected_bbox_for_frame(ITEM, 169) == (290, 668, 224, 45)


def test_before_first_and_after_last():
    assert protected_bbox_for_frame(ITEM, 100) == (300, 660, 220, 46)
    assert protected_bbox_for_frame(ITEM, 200) == (290, 668, 224, 45)


def test_fallback_to_aggregate_without_samples():
    item = {"bbox": [10, 20, 30, 40]}
    assert protected_bbox_for_frame(item, 7) == (10, 20, 30, 40)
