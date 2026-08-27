from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from app.core.translation.protocol import TranslationRequest, TranslationResult


class ProviderResponseError(RuntimeError):
    pass


def request_payload(
    segments: Sequence[TranslationRequest], target_language: str, glossary: Mapping[str, str]
) -> dict[str, object]:
    return {
        "target_language": target_language,
        "glossary": dict(glossary),
        "segments": [
            {
                "segment_id": item.segment_id,
                "source_text": item.source_text,
                "previous_text": item.previous_text,
                "next_text": item.next_text,
            }
            for item in segments
        ],
    }


def prompt_for_translation(
    segments: Sequence[TranslationRequest], target_language: str, glossary: Mapping[str, str]
) -> str:
    payload = request_payload(segments, target_language, glossary)
    return (
        "Translate Chinese dialogue subtitles. Return ONLY a JSON array. "
        "Each item must contain exactly segment_id, natural, optimized. "
        "natural is a faithful natural translation; optimized is concise subtitle-ready text. "
        "Do not add facts. Preserve names using glossary. Context is for meaning only; do not translate context as new segments.\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )


def parse_translation_results(text: str) -> list[TranslationResult]:
    raw = text.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderResponseError("translation provider returned invalid JSON") from exc
    if isinstance(payload, dict) and "results" in payload:
        payload = payload["results"]
    if not isinstance(payload, list):
        raise ProviderResponseError("translation response must be a JSON array")
    results: list[TranslationResult] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ProviderResponseError(f"translation item {index} is not an object")
        required = {"segment_id", "natural", "optimized"}
        if not required.issubset(item):
            raise ProviderResponseError(f"translation item {index} is missing required fields")
        values = {key: item[key] for key in required}
        if not all(isinstance(value, str) and value.strip() for value in values.values()):
            raise ProviderResponseError(f"translation item {index} contains empty/non-string fields")
        results.append(
            TranslationResult(
                segment_id=values["segment_id"].strip(),
                natural=values["natural"].strip(),
                optimized=values["optimized"].strip(),
            )
        )
    return results
