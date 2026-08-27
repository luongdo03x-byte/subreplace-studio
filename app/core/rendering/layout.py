from __future__ import annotations

from dataclasses import dataclass
import unicodedata

from .style import SubtitleStyle


@dataclass(frozen=True, slots=True)
class LayoutResult:
    lines: tuple[str, ...]
    font_size: int
    width_px: float


class SubtitleLayout:
    def __init__(self, *, min_font_scale: float = 0.78) -> None:
        if not 0.5 <= min_font_scale <= 1.0:
            raise ValueError("min_font_scale must be between 0.5 and 1.0")
        self.min_font_scale = min_font_scale

    def layout(self, text: str, style: SubtitleStyle, *, frame_size: tuple[int, int]) -> LayoutResult:
        frame_width, _ = frame_size
        clean = " ".join(text.split())
        if not clean:
            return LayoutResult(("",), style.font_size, 0.0)
        safe_width = float(frame_width) * style.max_width_ratio
        minimum = max(1, round(style.font_size * self.min_font_scale))
        for font_size in range(style.font_size, minimum - 1, -1):
            one_width = self._measure(clean, font_size)
            if one_width <= safe_width:
                return LayoutResult((clean,), font_size, one_width)
            lines = self._balanced_two_lines(clean, font_size)
            width = max(self._measure(line, font_size) for line in lines)
            if len(lines) <= 2 and width <= safe_width:
                return LayoutResult(tuple(lines), font_size, width)
        lines = self._balanced_two_lines(clean, minimum)
        return LayoutResult(tuple(lines[:2]), minimum, max(self._measure(line, minimum) for line in lines[:2]))

    @classmethod
    def _measure(cls, text: str, font_size: int) -> float:
        total = 0.0
        for char in text:
            if char.isspace():
                factor = 0.28
            elif unicodedata.east_asian_width(char) in {"W", "F"}:
                factor = 0.92
            elif char in "ilI.,'`!:;|":
                factor = 0.28
            elif char in "mwMW@%":
                factor = 0.82
            elif char.isupper():
                factor = 0.63
            else:
                factor = 0.52
            total += factor * font_size
        return total

    @classmethod
    def _balanced_two_lines(cls, text: str, font_size: int) -> list[str]:
        words = text.split()
        if len(words) < 2:
            return [text]
        best: tuple[float, int] | None = None
        for split in range(1, len(words)):
            left = " ".join(words[:split])
            right = " ".join(words[split:])
            left_width = cls._measure(left, font_size)
            right_width = cls._measure(right, font_size)
            score = max(left_width, right_width) + abs(left_width - right_width) * 0.12
            if best is None or score < best[0]:
                best = (score, split)
        assert best is not None
        split = best[1]
        return [" ".join(words[:split]), " ".join(words[split:])]
