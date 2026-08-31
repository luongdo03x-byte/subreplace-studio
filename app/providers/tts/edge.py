"""Microsoft Edge neural voices, reached through the edge-tts package."""
from __future__ import annotations

import asyncio
import time

from app.core.dubbing.protocol import SpeechSynthesisError

VOICE_FEMALE = "vi-VN-HoaiMyNeural"
VOICE_MALE = "vi-VN-NamMinhNeural"

DEFAULT_ATTEMPTS = 3
BACKOFF_SECONDS = (1.0, 3.0)


class EdgeTTSProvider:
    def __init__(self, *, attempts: int = DEFAULT_ATTEMPTS, sleep=time.sleep, communicate_factory=None) -> None:
        self.attempts = max(1, int(attempts))
        self._sleep = sleep
        self._factory = communicate_factory or self._default_factory

    @staticmethod
    def _default_factory(text: str, voice: str, rate: str):
        try:
            import edge_tts
        except ImportError as exc:  # pragma: no cover - covered by preflight
            raise SpeechSynthesisError("edge-tts is not installed") from exc
        return edge_tts.Communicate(text, voice, rate=rate)

    def synthesize(self, text: str, *, voice: str, rate: str = "+0%") -> bytes:
        clean = text.strip()
        if not clean:
            raise SpeechSynthesisError("cannot synthesize empty text")
        last: Exception | None = None
        for attempt in range(self.attempts):
            try:
                return self._collect(self._factory(clean, voice, rate))
            except Exception as exc:
                last = exc
                if attempt + 1 < self.attempts:
                    self._sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
        raise SpeechSynthesisError(f"edge-tts failed after {self.attempts} attempts: {last}")

    @staticmethod
    def _collect(communicate) -> bytes:
        async def drain() -> bytes:
            audio = bytearray()
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio":
                    audio.extend(chunk["data"])
            return bytes(audio)

        audio = asyncio.run(drain())
        if not audio:
            raise SpeechSynthesisError("edge-tts returned no audio")
        return audio
