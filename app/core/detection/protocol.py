from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True, slots=True)
class TextCandidate:
    bbox: tuple[int, int, int, int]
    polygon: tuple[tuple[int, int], ...]
    confidence: float
    frame_index: int


class TextDetector(Protocol):
    def detect(self, frame: np.ndarray, frame_index: int) -> list[TextCandidate]: ...
