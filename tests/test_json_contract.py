import json
from app.providers.translation.json_contract import parse_translation_results


def test_parse_translation_results_handles_int_segment_ids_and_fallbacks():
    raw = json.dumps([
        {"segment_id": 1, "natural": "Xin chao", "optimized": "Chao"},
        {"segment_id": "2", "natural": "Tam biet", "optimized": ""},
        {"segment_id": 3, "natural": "", "optimized": "Hen gap lai"},
        {"segment_id": 8, "natural": "", "optimized": "", "source_text": "山"},
    ])
    results = parse_translation_results(raw)
    assert len(results) == 4
    assert results[0].segment_id == "1"
    assert results[0].natural == "Xin chao"
    assert results[0].optimized == "Chao"

    # Fallback to natural when optimized is empty
    assert results[1].segment_id == "2"
    assert results[1].natural == "Tam biet"
    assert results[1].optimized == "Tam biet"

    # Fallback to optimized when natural is empty
    assert results[2].segment_id == "3"
    assert results[2].natural == "Hen gap lai"
    assert results[2].optimized == "Hen gap lai"

    # Fallback to source_text when both are empty
    assert results[3].segment_id == "8"
    assert results[3].natural == "山"
    assert results[3].optimized == "山"


def test_parse_translation_results_handles_wrapped_object():
    raw = json.dumps({
        "translations": [
            {"segment_id": "event-1", "natural": "Mot", "optimized": "Mot"}
        ]
    })
    results = parse_translation_results(raw)
    assert len(results) == 1
    assert results[0].segment_id == "event-1"
