from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence


@dataclass
class TranslationRequest:
    segment_id: str
    source_text: str
    previous_text: str
    next_text: str


@dataclass(frozen=True, slots=True)
class TranslationResult:
    segment_id: str
    natural: str
    optimized: str


class TranslationProvider(Protocol):
    def translate_batch(
        self,
        segments: Sequence[TranslationRequest],
        target_language: str,
        glossary: Mapping[str, str],
    ) -> list[TranslationResult]: ...
