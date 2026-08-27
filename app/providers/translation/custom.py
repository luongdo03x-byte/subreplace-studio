from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence

from app.core.translation.protocol import TranslationRequest, TranslationResult

from .json_contract import parse_translation_results, request_payload


class CustomAPITranslationProvider:
    def __init__(
        self,
        endpoint: str,
        *,
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        if not endpoint.startswith(("http://", "https://")):
            raise ValueError("custom translation endpoint must be http(s)")
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.headers = dict(headers or {})

    def translate_batch(
        self,
        segments: Sequence[TranslationRequest],
        target_language: str,
        glossary: Mapping[str, str],
    ) -> list[TranslationResult]:
        payload = request_payload(segments, target_language, glossary)
        headers = {"Content-Type": "application/json", "Accept": "application/json", **self.headers}
        if self.api_key:
            headers.setdefault("Authorization", f"Bearer {self.api_key}")
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"custom translation API failed: {exc}") from exc
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            return parse_translation_results(raw)
        if isinstance(decoded, dict) and "results" in decoded:
            return parse_translation_results(json.dumps(decoded["results"], ensure_ascii=False))
        return parse_translation_results(raw)
