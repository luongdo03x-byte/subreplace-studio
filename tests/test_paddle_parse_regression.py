"""Regression: PaddleOCR 3.x returns plural keys rec_texts/rec_scores.

v0.2.1 _parse_prediction only read rec_text/text -> empty OCR results on
PaddleOCR 3.7 despite successful inference. Guard: all formats must parse.
"""
from app.providers.ocr.paddle import PaddleOCRProvider


def test_paddleocr3_plural_keys():
    raw = [{
        "rec_texts": ["\u65e2\u7136\u9192\u4e86", "TG@svipktv"],
        "rec_scores": [0.93, 0.99],
    }]
    text, score = PaddleOCRProvider._parse_prediction(raw)
    assert text == "TG@svipktv", f"expected best-score text, got {text!r}"
    assert abs(score - 0.99) < 1e-6


def test_singular_keys_still_supported():
    raw = [{"rec_text": ["A", "B"], "rec_score": [0.5, 0.8]}]
    text, score = PaddleOCRProvider._parse_prediction(raw)
    assert text == "B"
    assert abs(score - 0.8) < 1e-6


def test_empty_result():
    text, score = PaddleOCRProvider._parse_prediction([{"rec_texts": [], "rec_scores": []}])
    assert text == "" and score == 0.0
