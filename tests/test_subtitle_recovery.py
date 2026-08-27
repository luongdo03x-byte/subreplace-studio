import cv2
import numpy as np

from app.core.detection.recovery import recover_missing_events


def test_recovers_changed_line_and_extends_matching_neighbor(tmp_path):
    path = tmp_path / "recovery.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 25.0, (480, 240))
    assert writer.isOpened()
    for index in range(30):
        frame = np.full((240, 480, 3), (45, 80, 120), np.uint8)
        if 2 <= index <= 11:
            cv2.putText(frame, "LINE ONE", (95, 185), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 4)
        elif 12 <= index <= 24:
            cv2.putText(frame, "LINE TWO", (90, 185), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 4)
        writer.write(frame)
    writer.release()

    events = [{
        "event_id": "known",
        "start_frame": 2,
        "end_frame": 7,
        "text": "第一行",
        "confidence": 0.9,
        "bbox": [0, 145, 480, 60],
        "anchor_bbox": [95, 155, 260, 40],
        "text_type": "dialogue_subtitle",
        "review_status": "auto",
    }]

    def recognize(_frame, _regions, frame_index):
        return ("第一行", 0.9) if frame_index <= 11 else ("第二行", 0.9)

    recovered = recover_missing_events(str(path), events, recognize)
    known = next(item for item in recovered if item["event_id"] == "known")
    added = [item for item in recovered if item.get("recovered")]
    assert known["end_frame"] == 11
    assert len(added) == 1
    assert added[0]["start_frame"] == 12
    assert added[0]["end_frame"] == 24
    assert added[0]["text"] == "第二行"


def test_rejects_non_cjk_candidate(tmp_path):
    path = tmp_path / "watermark.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 25.0, (480, 240))
    assert writer.isOpened()
    for _ in range(8):
        frame = np.full((240, 480, 3), 50, np.uint8)
        cv2.putText(frame, "TG@handle", (120, 185), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 3)
        writer.write(frame)
    writer.release()
    recovered = recover_missing_events(str(path), [], lambda *_args: ("TG@handle", 0.99))
    assert recovered == []
