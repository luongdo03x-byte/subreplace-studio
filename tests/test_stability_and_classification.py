"""Regression guards for v0.2.1 pipeline quality fixes.

A) TextEventScanner must not promote unstable (< stable_after_samples)
   detections into persisted text events. On test_10s.mp4, 87.6% of events
   were 1-sample noise which flooded protected masks and blocked dialogue
   erasure (protected_collision=43).
B) TextClassifier must gate dialogue AUTO approval on OCR confidence:
   - < 0.35 -> UNKNOWN / needs_review (matches reconciliation floor)
   - < 0.50 -> dialogue kept but needs_review
   '家' with ocr confidence 0.08 previously became auto-dialogue.
"""
import numpy as np

from app.core.detection.protocol import TextCandidate
from app.core.detection.classification import TextClassifier
from app.core.ocr.events import EventScannerConfig, TextEventScanner
from app.models.text_track import TextTrack


def _candidate(x, y, w, h, conf=0.9, frame_index=0):
    poly = ((x, y), (x + w, y), (x + w, y + h), (x, y + h))
    return TextCandidate(bbox=(x, y, w, h), polygon=poly, confidence=conf, frame_index=frame_index)


def _frame():
    return np.zeros((100, 100, 3), dtype=np.uint8)


def test_scanner_drops_single_sample_noise():
    scanner = TextEventScanner(EventScannerConfig())
    closed = []
    closed += scanner.update(_frame(), [_candidate(10, 10, 20, 10)], frame_index=0, scene_id=0)
    closed += scanner.update(_frame(), [], frame_index=5, scene_id=0)  # grace
    closed += scanner.update(_frame(), [], frame_index=10, scene_id=0)  # beyond grace
    closed += scanner.finalize()
    assert closed == [], f"unstable noise must not become an event: {closed}"


def test_scanner_keeps_stable_event():
    scanner = TextEventScanner(EventScannerConfig(stable_after_samples=3))
    closed = []
    for i in range(6):
        closed += scanner.update(_frame(), [_candidate(10, 10, 20, 10)], frame_index=i * 5, scene_id=0)
    closed += scanner.update(_frame(), [], frame_index=40, scene_id=0)
    closed += scanner.update(_frame(), [], frame_index=45, scene_id=0)
    closed += scanner.update(_frame(), [], frame_index=50, scene_id=0)
    closed += scanner.finalize()
    assert len(closed) == 1 and len(closed[0].samples) >= 3


def test_scanner_never_surfaces_unstable_events():
    scanner = TextEventScanner(EventScannerConfig(stable_after_samples=6, missing_grace_frames=0))
    closed = scanner.update(_frame(), [_candidate(5, 5, 30, 12, conf=0.99)], frame_index=0, scene_id=0)
    closed += scanner.update(_frame(), [_candidate(5, 5, 30, 12, conf=0.99)], frame_index=1, scene_id=0)
    assert closed == [], "2-sample event below stable_after_samples must not surface"


def test_low_confidence_dialogue_becomes_unknown():
    cls = TextClassifier()
    track = TextTrack(id="t", frame_indices=[0, 1, 2], bboxes=[(300, 900, 200, 60)] * 3)
    result = cls.classify(track, frame_size=(720, 1280), total_frames=250,
                          recognized_text="家", speech_overlap=0.0, ocr_confidence=0.08)
    assert result.text_type.value == "unknown", result
    assert result.review_status.value == "needs_review", result


def test_mid_confidence_dialogue_needs_review_but_typed():
    cls = TextClassifier()
    track = TextTrack(id="t", frame_indices=[0, 1, 2], bboxes=[(300, 900, 200, 60)] * 3)
    result = cls.classify(track, frame_size=(720, 1280), total_frames=250,
                          recognized_text="上店", speech_overlap=0.0, ocr_confidence=0.42)
    assert result.text_type.value == "dialogue_subtitle", result
    assert result.review_status.value == "needs_review", result


def test_high_confidence_dialogue_still_auto():
    cls = TextClassifier()
    track = TextTrack(id="t", frame_indices=[0, 1, 2], bboxes=[(300, 900, 200, 60)] * 3)
    result = cls.classify(track, frame_size=(720, 1280), total_frames=250,
                          recognized_text="放肆", speech_overlap=0.0, ocr_confidence=1.0)
    assert result.text_type.value == "dialogue_subtitle", result
    assert result.review_status.value == "auto", result


def test_latin_handle_never_auto_dialogue():
    cls = TextClassifier()
    track = TextTrack(id="t", frame_indices=list(range(25)), bboxes=[(273, 1047, 231, 59)] * 25)
    result = cls.classify(track, frame_size=(720, 1280), total_frames=1502,
                          recognized_text="TG@svipktv", speech_overlap=0.6, ocr_confidence=1.0)
    assert result.text_type.value == "watermark", result
    assert result.review_status.value == "auto", result


def test_short_latin_id_never_auto_dialogue():
    cls = TextClassifier()
    track = TextTrack(id="t", frame_indices=list(range(34)), bboxes=[(131, 1074, 112, 54)] * 34)
    result = cls.classify(track, frame_size=(720, 1280), total_frames=1502,
                          recognized_text="svip", speech_overlap=0.8, ocr_confidence=1.0)
    assert result.text_type.value != "dialogue_subtitle" or result.review_status.value != "auto", result
