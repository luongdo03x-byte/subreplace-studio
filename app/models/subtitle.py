from __future__ import annotations

from dataclasses import dataclass

from .enums import ReviewStatus, TextType


@dataclass(slots=True)
class SubtitleSegment:
    id: str
    start_ms: int
    end_ms: int
    source_language: str
    source_text: str
    target_language: str
    natural_translation: str = ""
    subtitle_optimized_translation: str = ""
    text_type: TextType = TextType.DIALOGUE_SUBTITLE
    ocr_confidence: float = 0.0
    asr_confidence: float = 0.0
    asr_match: float = 0.0
    classification_confidence: float = 0.0
    review_status: ReviewStatus = ReviewStatus.AUTO
    track_id: str | None = None
    mask_track_id: str | None = None
    anchor: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("subtitle timing must satisfy 0 <= start_ms < end_ms")
        if self.target_language not in {"vi", "en"}:
            raise ValueError("target_language must be 'vi' or 'en'")

    @property
    def translated_text(self) -> str:
        return self.subtitle_optimized_translation or self.natural_translation
