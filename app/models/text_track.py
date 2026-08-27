from __future__ import annotations

from dataclasses import dataclass, field

from .enums import ERASABLE_TYPES, ReviewStatus, TextType


@dataclass(slots=True)
class TextTrack:
    id: str
    text_type: TextType = TextType.UNKNOWN
    review_status: ReviewStatus = ReviewStatus.AUTO
    classification_confidence: float = 0.0
    frame_indices: list[int] = field(default_factory=list)
    bboxes: list[tuple[int, int, int, int]] = field(default_factory=list)

    @property
    def is_erasable(self) -> bool:
        return (
            self.text_type in ERASABLE_TYPES
            and self.review_status is not ReviewStatus.NEEDS_REVIEW
        )
