from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ASRSegment:
    start_ms: int
    end_ms: int
    text: str
    confidence: float


class ASRProvider(Protocol):
    def transcribe(self, audio_path: str, language: str = "zh") -> list[ASRSegment]: ...
