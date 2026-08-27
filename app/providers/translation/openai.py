from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.core.translation.protocol import TranslationRequest, TranslationResult
from app.providers.errors import ProviderUnavailableError

from .json_contract import parse_translation_results, prompt_for_translation


class OpenAITranslationProvider:
    def __init__(self, *, client: Any | None = None, model: str = "gpt-5.6", api_key: str | None = None) -> None:
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise ProviderUnavailableError("OpenAI provider requires the optional 'openai' package") from exc
            client = OpenAI(api_key=api_key) if api_key else OpenAI()
        self.client = client
        self.model = model

    def translate_batch(
        self,
        segments: Sequence[TranslationRequest],
        target_language: str,
        glossary: Mapping[str, str],
    ) -> list[TranslationResult]:
        response = self.client.responses.create(
            model=self.model,
            input=prompt_for_translation(segments, target_language, glossary),
        )
        output_text = getattr(response, "output_text", None)
        if not isinstance(output_text, str):
            raise RuntimeError("OpenAI response did not expose output_text")
        return parse_translation_results(output_text)
