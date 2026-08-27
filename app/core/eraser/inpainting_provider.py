from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True, slots=True)
class InpaintingContext:
    fps: float = 24.0
    fp16: bool = False


@dataclass(frozen=True, slots=True)
class InpaintingResult:
    frames: tuple[np.ndarray, ...]
    provider_name: str
    stdout: str = ""


class InpaintingProvider(Protocol):
    @property
    def name(self) -> str: ...

    def inpaint(
        self,
        frames: list[np.ndarray],
        masks: list[np.ndarray],
        context: InpaintingContext,
    ) -> InpaintingResult: ...
