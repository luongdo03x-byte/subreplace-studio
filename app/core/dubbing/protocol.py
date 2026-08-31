"""Boundary between dubbing rules and whatever speaks the words."""
from __future__ import annotations

from typing import Protocol


class SpeechSynthesisError(RuntimeError):
    pass


class SpeechSynthesizer(Protocol):
    def synthesize(self, text: str, *, voice: str, rate: str = "+0%") -> bytes:
        """Return encoded audio (MP3) for one line of dialogue."""
        ...
