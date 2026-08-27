from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from app.models.subtitle import SubtitleSegment

from .layout import SubtitleLayout
from .style import SubtitleStyle


def _ass_time(ms: int) -> str:
    centiseconds = max(0, int(round(ms / 10)))
    hours, rem = divmod(centiseconds, 360000)
    minutes, rem = divmod(rem, 6000)
    seconds, cs = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{cs:02d}"


def _srt_time(ms: int) -> str:
    ms = max(0, int(ms))
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _escape_ass(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def write_srt(path: Path, segments: Sequence[SubtitleSegment]) -> Path:
    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        text = segment.translated_text.strip()
        if not text:
            continue
        lines.extend([
            str(index),
            f"{_srt_time(segment.start_ms)} --> {_srt_time(segment.end_ms)}",
            text,
            "",
        ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_ass(
    path: Path,
    segments: Sequence[SubtitleSegment],
    style: SubtitleStyle,
    *,
    frame_size: tuple[int, int],
) -> Path:
    width, height = frame_size
    layout = SubtitleLayout()
    events: list[str] = []
    for segment in segments:
        text = segment.translated_text.strip()
        if not text:
            continue
        laid_out = layout.layout(text, style, frame_size=frame_size)
        rendered = r"\N".join(_escape_ass(line) for line in laid_out.lines)
        override = f"{{\\fs{laid_out.font_size}}}"
        if segment.anchor is not None:
            # Anchor at the original burned-in subtitle's bottom-center so the
            # replacement line occupies the same position instead of the
            # default bottom margin.
            cx = min(max(0, int(segment.anchor[0])), width)
            cy = min(max(0, int(segment.anchor[1])), height)
            override = f"{{\\pos({cx},{cy})\\fs{laid_out.font_size}}}"
        events.append(
            f"Dialogue: 0,{_ass_time(segment.start_ms)},{_ass_time(segment.end_ms)},Default,,0,0,0,,{override}{rendered}"
        )
    content = "\n".join([
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        f"Style: Default,{style.font_name},{style.font_size},{style.fill_color},&H000000FF,{style.outline_color},&H80000000,0,0,0,0,100,100,0,0,1,{style.outline_width},{style.shadow},{style.alignment},24,24,{style.margin_bottom},1",
        "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
        *events,
        "",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
