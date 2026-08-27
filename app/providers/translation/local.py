from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence

from app.core.translation.protocol import TranslationRequest, TranslationResult

from .json_contract import parse_translation_results, request_payload


class LocalCommandTranslationProvider:
    def __init__(self, command: Sequence[str], *, timeout_seconds: float = 120.0) -> None:
        if not command:
            raise ValueError("local translation command cannot be empty")
        self.command = list(command)
        self.timeout_seconds = timeout_seconds

    def translate_batch(
        self,
        segments: Sequence[TranslationRequest],
        target_language: str,
        glossary: Mapping[str, str],
    ) -> list[TranslationResult]:
        payload = request_payload(segments, target_language, glossary)
        proc = subprocess.run(
            self.command,
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            check=False,
            timeout=self.timeout_seconds,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"local translation command failed: {proc.stderr[-2000:]}")
        return parse_translation_results(proc.stdout)
