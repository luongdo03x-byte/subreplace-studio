from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True, slots=True)
class OCRResult:
    text: str
    confidence: float
    frame_index: int


class OCRProvider(Protocol):
    def recognize(
        self,
        frame: np.ndarray,
        regions: list[tuple[int, int, int, int]],
        *,
        frame_index: int = 0,
    ) -> list[OCRResult]: ...
