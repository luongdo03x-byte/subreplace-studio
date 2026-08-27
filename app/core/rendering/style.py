from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SubtitleStyle:
    font_name: str = "DejaVu Sans"
    font_size: int = 42
    fill_color: str = "&H00FFFFFF"
    outline_color: str = "&H00101010"
    outline_width: float = 2.0
    shadow: float = 0.5
    alignment: int = 2
    max_width_ratio: float = 0.88
    margin_bottom: int = 42
    line_spacing: float = 1.0

    def __post_init__(self) -> None:
        if self.font_size <= 0:
            raise ValueError("font_size must be positive")
        if not 0.35 <= self.max_width_ratio <= 1.0:
            raise ValueError("max_width_ratio must be between 0.35 and 1.0")
        if self.outline_width < 0 or self.shadow < 0:
            raise ValueError("outline/shadow must be non-negative")
