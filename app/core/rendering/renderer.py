from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
import shutil
import subprocess
import tempfile

from app.core.media.ffmpeg import FFmpegMedia, MediaError
from app.models.subtitle import SubtitleSegment

from .ass import write_ass, write_srt
from .placement import SubtitlePlacement
from .style import SubtitleStyle


class RenderError(RuntimeError):
    pass


def build_filter_complex(*, ass_path: str, dubbed: bool, duck_ratio: int) -> str:
    """Filtergraph that burns subtitles and, when dubbing, ducks the original audio.

    Returns "" when there is no dub track: that path keeps the historical
    -vf/-c:a copy command, so a subtitle-only render never re-encodes audio.
    """
    if not dubbed:
        return ""
    if duck_ratio <= 0:
        raise ValueError("duck_ratio must be positive")
    return (
        f"[0:v]ass={ass_path}[v];"
        "[0:a]aresample=48000[orig];"
        # apad keeps the dub input from ending sidechaincompress (and thus the
        # whole mix) early: without it, encoder padding that lets the audio
        # stream slightly outlast the video stream truncates the output.
        "[1:a]aresample=48000,apad[dub];"
        f"[orig][dub]sidechaincompress=threshold=0.02:ratio={duck_ratio}:attack=20:release=400[ducked];"
        "[ducked][dub]amix=inputs=2:duration=first:normalize=0[aout]"
    )


@dataclass(frozen=True, slots=True)
class RenderResult:
    output_path: Path
    srt_path: Path
    placement_report: dict[str, object] = field(default_factory=dict)


class SubtitleRenderer:
    def __init__(self, *, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe") -> None:
        self.media = FFmpegMedia(ffmpeg=ffmpeg, ffprobe=ffprobe)
        self.ffmpeg = ffmpeg

    def export(
        self,
        *,
        video: str | Path,
        segments: Sequence[SubtitleSegment],
        style: SubtitleStyle,
        output_path: str | Path,
        srt_path: str | Path,
        placement: SubtitlePlacement,
        dub_audio_path: str | Path | None = None,
        duck_ratio: int = 12,
    ) -> RenderResult:
        source = Path(video)
        output = Path(output_path)
        srt = Path(srt_path)
        if not source.is_file():
            raise RenderError(f"render source video does not exist: {source}")
        try:
            metadata = self.media.probe(source)
        except MediaError as exc:
            raise RenderError(str(exc)) from exc
        output.parent.mkdir(parents=True, exist_ok=True)
        write_srt(srt, segments)
        ffmpeg = shutil.which(self.ffmpeg)
        if ffmpeg is None:
            raise RenderError(f"required renderer binary is not installed: {self.ffmpeg}")
        dub = Path(dub_audio_path) if dub_audio_path else None
        # A truncated or zero-byte track (an interrupted synthesis write, picked
        # up by a retry) must fall back to the subtitle-only render rather than
        # feed an undecodable stream into the filtergraph.
        dubbed = self._dub_is_usable(dub) and metadata.has_audio
        with tempfile.TemporaryDirectory(prefix="subreplace-render-") as tmp:
            ass_path = Path(tmp) / "target.ass"
            placement_report = write_ass(
                ass_path, segments, style,
                frame_size=(metadata.width, metadata.height), placement=placement,
            )
            escaped = self._escape_filter_path(ass_path)
            command = [ffmpeg, "-y", "-i", str(source)]
            if dubbed:
                command += ["-i", str(dub)]
                command += [
                    "-filter_complex",
                    build_filter_complex(ass_path=escaped, dubbed=True, duck_ratio=duck_ratio),
                    "-map", "[v]", "-map", "[aout]",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                    "-c:a", "aac", "-b:a", "192k",
                ]
            else:
                command += [
                    "-vf", f"ass={escaped}",
                    "-map", "0:v:0", "-map", "0:a?",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                    "-c:a", "copy",
                ]
            command += ["-movflags", "+faststart", str(output)]
            proc = subprocess.run(command, text=True, capture_output=True, check=False)
            if proc.returncode != 0:
                raise RenderError(f"subtitle render failed: {proc.stderr[-3000:]}")
        if not output.is_file() or output.stat().st_size == 0:
            raise RenderError("renderer did not produce a non-empty output video")
        return RenderResult(output_path=output, srt_path=srt, placement_report=placement_report)

    @staticmethod
    def _escape_filter_path(path: Path) -> str:
        # ffmpeg filtergraph escaping, including Windows drive separator.
        return str(path.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")

    @staticmethod
    def _dub_is_usable(path: Path | None) -> bool:
        # A missing or zero-byte file (e.g. an interrupted synthesis write
        # picked up by a retry) is undecodable and must not be treated as a
        # usable dub track.
        return path is not None and path.is_file() and path.stat().st_size > 0
