from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.core.translation.protocol import TranslationRequest, TranslationResult
from app.providers.errors import ProviderUnavailableError

from .json_contract import parse_translation_results, prompt_for_translation


class GeminiTranslationProvider:
    def __init__(self, *, client: Any | None = None, model: str = "gemini-2.5-flash", api_key: str | None = None) -> None:
        if client is None:
            try:
                from google import genai
            except ImportError as exc:
                raise ProviderUnavailableError("Gemini provider requires the optional 'google-genai' package") from exc
            client = genai.Client(api_key=api_key) if api_key else genai.Client()
        self.client = client
        self.model = model

    def translate_batch(
        self,
        segments: Sequence[TranslationRequest],
        target_language: str,
        glossary: Mapping[str, str],
    ) -> list[TranslationResult]:
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt_for_translation(segments, target_language, glossary),
        )
        text = getattr(response, "text", None)
        if not isinstance(text, str):
            raise RuntimeError("Gemini response did not expose text")
        return parse_translation_results(text)
