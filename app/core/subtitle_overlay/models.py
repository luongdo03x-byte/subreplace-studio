from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Cue:
    id: str
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True)
class LockedLayout:
    y: int
    extra_height: int
    fallback: bool
    measured_frames: int
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class RenderProfile:
    width: int
    height: int
    fps_num: int
    fps_den: int
    audio_mode: str


@dataclass(frozen=True)
class DisplayCue:
    source_id: str
    start_ms: int
    end_ms: int
    lines: tuple[str, ...]


@dataclass(frozen=True)
class OverlayStyle:
    font_path: Path
    font_name: str = 'Be Vietnam Pro'
    font_size: int = 48
    fill: str = '&H0000FFFF'
    outline_color: str = '&H00000000'
    outline: int = 3
    shadow: int = 2
    margin_x: int = 40
