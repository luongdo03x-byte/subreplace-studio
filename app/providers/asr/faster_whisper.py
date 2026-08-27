from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from app.core.asr.protocol import ASRSegment
from app.providers.errors import ProviderUnavailableError


class FasterWhisperProvider:
    def __init__(
        self,
        model_size: str = "small",
        *,
        device: str = "cpu",
        compute_type: str | None = None,
        model: Any | None = None,
    ) -> None:
        if model is not None:
            self.model = model
            return
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise ProviderUnavailableError("faster-whisper is not installed; install the 'ai' dependencies") from exc
        compute = compute_type or ("float16" if device == "cuda" else "int8")
        self.model = WhisperModel(model_size, device=device, compute_type=compute)

    def transcribe(self, audio_path: str, language: str = "zh") -> list[ASRSegment]:
        if not Path(audio_path).is_file():
            raise FileNotFoundError(audio_path)
        segments, _ = self.model.transcribe(
            audio_path,
            beam_size=5,
            language=language,
            vad_filter=True,
        )
        output: list[ASRSegment] = []
        for segment in segments:  # faster-whisper starts inference while consuming this generator.
            avg_logprob = float(getattr(segment, "avg_logprob", -0.7))
            confidence = float(max(0.0, min(1.0, math.exp(min(0.0, avg_logprob)))))
            output.append(
                ASRSegment(
                    start_ms=int(round(float(segment.start) * 1000)),
                    end_ms=int(round(float(segment.end) * 1000)),
                    text=str(segment.text).strip(),
                    confidence=confidence,
                )
            )
        return output
