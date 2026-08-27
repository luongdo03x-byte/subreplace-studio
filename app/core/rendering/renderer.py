from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import tempfile

from app.core.media.ffmpeg import FFmpegMedia, MediaError
from app.models.subtitle import SubtitleSegment

from .ass import write_ass, write_srt
from .style import SubtitleStyle


class RenderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RenderResult:
    output_path: Path
    srt_path: Path


class SubtitleRenderer:
    def __init__(self, *, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe") -> None:
        self.media = FFmpegMedia(ffmpeg=ffmpeg, ffprobe=ffprobe)
        self.ffmpeg = ffmpeg

    def export(
        self,
        *,
        clean_video: str | Path,
        segments: Sequence[SubtitleSegment],
        style: SubtitleStyle,
        output_path: str | Path,
        srt_path: str | Path,
    ) -> RenderResult:
        clean = Path(clean_video)
        output = Path(output_path)
        srt = Path(srt_path)
        if not clean.is_file():
            raise RenderError(f"clean video does not exist: {clean}")
        try:
            metadata = self.media.probe(clean)
        except MediaError as exc:
            raise RenderError(str(exc)) from exc
        output.parent.mkdir(parents=True, exist_ok=True)
        write_srt(srt, segments)
        ffmpeg = shutil.which(self.ffmpeg)
        if ffmpeg is None:
            raise RenderError(f"required renderer binary is not installed: {self.ffmpeg}")
        with tempfile.TemporaryDirectory(prefix="subreplace-render-") as tmp:
            ass_path = Path(tmp) / "target.ass"
            write_ass(ass_path, segments, style, frame_size=(metadata.width, metadata.height))
            command = [
                ffmpeg,
                "-y",
                "-i",
                str(clean),
                "-vf",
                f"ass={self._escape_filter_path(ass_path)}",
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-c:a",
                "copy",
                "-movflags",
                "+faststart",
                str(output),
            ]
            proc = subprocess.run(command, text=True, capture_output=True, check=False)
            if proc.returncode != 0:
                raise RenderError(f"subtitle render failed: {proc.stderr[-3000:]}")
        if not output.is_file() or output.stat().st_size == 0:
            raise RenderError("renderer did not produce a non-empty output video")
        return RenderResult(output_path=output, srt_path=srt)

    @staticmethod
    def _escape_filter_path(path: Path) -> str:
        # ffmpeg filtergraph escaping, including Windows drive separator.
        return str(path.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
