from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re

from .protocol import OCRResult


@dataclass(frozen=True, slots=True)
class OCRConsensus:
    text: str
    confidence: float
    support: int


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text.strip())


def choose_consensus(results: list[OCRResult]) -> OCRConsensus:
    if not results:
        return OCRConsensus("", 0.0, 0)
    groups: dict[str, list[OCRResult]] = defaultdict(list)
    for result in results:
        normalized = _normalize(result.text)
        if normalized:
            groups[normalized].append(result)
    if not groups:
        return OCRConsensus("", 0.0, 0)
    ranked = sorted(
        groups.items(),
        key=lambda item: (sum(r.confidence for r in item[1]), len(item[1]), max(r.confidence for r in item[1])),
        reverse=True,
    )
    text, winning = ranked[0]
    return OCRConsensus(text, float(sum(r.confidence for r in winning) / len(winning)), len(winning))
