from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.models.subtitle import SubtitleSegment

from .protocol import TranslationProvider, TranslationRequest, TranslationResult


class TranslationError(RuntimeError):
    pass


class TranslationService:
    def __init__(self, provider: TranslationProvider) -> None:
        self.provider = provider

    def translate(
        self,
        segments: Sequence[SubtitleSegment],
        *,
        target_language: str,
        glossary: Mapping[str, str],
    ) -> list[SubtitleSegment]:
        if target_language not in {"vi", "en"}:
            raise TranslationError("target language must be 'vi' or 'en'")
        requests = [
            TranslationRequest(
                segment_id=item.id,
                source_text=item.source_text,
                previous_text=segments[index - 1].source_text if index > 0 else "",
                next_text=segments[index + 1].source_text if index + 1 < len(segments) else "",
            )
            for index, item in enumerate(segments)
        ]
        results = self.provider.translate_batch(requests, target_language, dict(glossary))
        self._validate_results(requests, results)
        by_id = {item.segment_id: item for item in results}
        translated = list(segments)
        for segment in translated:
            result = by_id[segment.id]
            segment.target_language = target_language
            segment.natural_translation = result.natural.strip()
            segment.subtitle_optimized_translation = result.optimized.strip()
        return translated

    @staticmethod
    def _validate_results(
        requests: Sequence[TranslationRequest], results: Sequence[TranslationResult]
    ) -> None:
        expected = [item.segment_id for item in requests]
        actual = [item.segment_id for item in results]
        if len(actual) != len(set(actual)):
            raise TranslationError("translation provider returned duplicate segment IDs")
        if set(actual) != set(expected):
            raise TranslationError(
                f"translation provider returned mismatched segment IDs: expected {expected!r}, got {actual!r}"
            )
        for item in results:
            if not item.natural.strip() or not item.optimized.strip():
                raise TranslationError(f"empty translation for segment {item.segment_id}")
