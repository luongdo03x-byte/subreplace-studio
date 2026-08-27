from app.core.translation.coalesce import coalesce_dialogue_events


def _event(event_id, start, end, text, bbox):
    return {
        "event_id": event_id, "start_frame": start, "end_frame": end,
        "text": text, "confidence": 0.9, "bbox": bbox, "anchor_bbox": bbox,
        "text_type": "dialogue_subtitle", "review_status": "auto",
    }


def test_coalesces_simultaneous_horizontal_fragments():
    events = [
        _event("left", 100, 130, "你个小", [90, 840, 170, 60]),
        _event("right", 120, 140, "太监不要忘了", [280, 840, 350, 60]),
    ]
    result = coalesce_dialogue_events(events)
    assert len(result) == 1
    assert result[0]["text"] == "你个小太监不要忘了"
    assert result[0]["start_frame"] == 100
    assert result[0]["end_frame"] == 140


def test_keeps_centered_successive_lines_separate():
    events = [
        _event("first", 100, 125, "第一句话", [180, 840, 360, 60]),
        _event("second", 123, 150, "第二句话", [182, 840, 356, 60]),
    ]
    assert len(coalesce_dialogue_events(events)) == 2


def test_drops_fragment_contained_in_complete_text():
    events = [
        _event("complete", 100, 140, "被兵部尚书", [180, 840, 360, 60]),
        _event("fragment", 110, 120, "兵部", [90, 840, 60, 60]),
    ]
    result = coalesce_dialogue_events(events)
    assert len(result) == 1
    assert result[0]["text"] == "被兵部尚书"


def test_merges_identical_lines_separated_by_short_detection_gap():
    events = [
        _event("first", 100, 120, "既然醒了", [180, 840, 360, 60]),
        _event("second", 124, 150, "既然醒了", [182, 840, 356, 60]),
    ]
    result = coalesce_dialogue_events(events)
    assert len(result) == 1
    assert result[0]["start_frame"] == 100
    assert result[0]["end_frame"] == 150


def test_drops_isolated_single_character_false_positives():
    events = [
        _event("line", 50, 80, "还不赶紧过来", [180, 840, 360, 66]),
        _event("decor", 100, 145, "福", [410, 376, 56, 57]),
        _event("flash", 110, 116, "福", [411, 903, 68, 46]),
    ]
    result = coalesce_dialogue_events(events)
    assert [item["event_id"] for item in result] == ["line"]


def test_keeps_valid_single_character_subtitle():
    events = [
        _event("context", 50, 80, "前一句话", [180, 840, 360, 66]),
        _event("single", 100, 121, "你", [480, 846, 59, 60]),
    ]
    result = coalesce_dialogue_events(events)
    assert [item["event_id"] for item in result] == ["context", "single"]


def test_keeps_short_singleton_when_it_belongs_to_phrase():
    events = [
        _event("prefix", 100, 106, "已", [120, 840, 40, 60]),
        _event("phrase", 100, 130, "被兵部尚书", [180, 840, 360, 60]),
    ]
    result = coalesce_dialogue_events(events)
    assert len(result) == 1
    assert result[0]["text"] == "已被兵部尚书"
