from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    final_source_text: str
    ocr_confidence: float
    asr_match: float
    final_confidence: float
    used_asr_text: bool


def _normalize(value: str) -> str:
    return re.sub(r"[\s，。！？,.!?;；:'\"“”‘’]", "", value)


class Reconciler:
    def reconcile(
        self,
        *,
        ocr_text: str,
        ocr_confidence: float,
        asr_text: str,
        asr_confidence: float,
        timestamp_overlap: float,
    ) -> ReconciliationResult:
        ocr_norm, asr_norm = _normalize(ocr_text), _normalize(asr_text)
        similarity = SequenceMatcher(None, ocr_norm, asr_norm).ratio() if ocr_norm and asr_norm else 0.0
        match = float(similarity * max(0.0, min(timestamp_overlap, 1.0)))
        use_asr = bool(
            asr_text.strip()
            and ocr_confidence < 0.35
            and asr_confidence >= 0.60
            and match >= 0.70
        )
        if use_asr:
            text = asr_text.strip()
            confidence = 0.65 * asr_confidence + 0.35 * match
        elif ocr_text.strip():
            text = ocr_text.strip()
            confidence = 0.75 * ocr_confidence + 0.25 * (asr_confidence * match)
        else:
            text = asr_text.strip()
            confidence = asr_confidence * max(timestamp_overlap, 0.5) if text else 0.0
        return ReconciliationResult(text, float(ocr_confidence), match, float(min(confidence, 1.0)), use_asr)
