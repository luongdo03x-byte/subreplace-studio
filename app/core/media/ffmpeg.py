from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path


class MediaError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class VideoMetadata:
    width: int
    height: int
    fps: float
    frame_count: int
    duration_ms: int
    codec: str
    has_audio: bool


class FFmpegMedia:
    def __init__(self, *, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe") -> None:
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe

    def _binary(self, name: str) -> str:
        resolved = shutil.which(name)
        if resolved is None:
            raise MediaError(f"required media binary is not installed: {name}")
        return resolved

    def probe(self, path: str | Path) -> VideoMetadata:
        media = Path(path)
        if not media.is_file():
            raise MediaError(f"media file does not exist: {media}")
        command = [
            self._binary(self.ffprobe),
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(media),
        ]
        proc = subprocess.run(command, text=True, capture_output=True, check=False)
        if proc.returncode != 0:
            raise MediaError(f"ffprobe failed for {media}: {proc.stderr.strip()}")
        try:
            payload = json.loads(proc.stdout)
            streams = payload.get("streams", [])
            video = next(stream for stream in streams if stream.get("codec_type") == "video")
        except (json.JSONDecodeError, StopIteration, TypeError) as exc:
            raise MediaError(f"no decodable video stream in {media}") from exc
        rate = video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1"
        try:
            fps = float(Fraction(rate))
        except (ValueError, ZeroDivisionError):
            fps = 0.0
        duration_s = float(video.get("duration") or payload.get("format", {}).get("duration") or 0.0)
        raw_frames = video.get("nb_frames")
        frame_count = int(raw_frames) if raw_frames not in (None, "N/A") else int(round(duration_s * fps))
        has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
        return VideoMetadata(
            width=int(video["width"]),
            height=int(video["height"]),
            fps=fps,
            frame_count=frame_count,
            duration_ms=int(round(duration_s * 1000)),
            codec=str(video.get("codec_name") or "unknown"),
            has_audio=has_audio,
        )

    def extract_audio(self, source: str | Path, output: str | Path) -> Path:
        source_path, output_path = Path(source), Path(output)
        if not source_path.is_file():
            raise MediaError(f"media file does not exist: {source_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            self._binary(self.ffmpeg), "-y", "-i", str(source_path), "-vn", "-acodec", "pcm_s16le", str(output_path)
        ]
        proc = subprocess.run(command, text=True, capture_output=True, check=False)
        if proc.returncode != 0:
            raise MediaError(f"audio extraction failed: {proc.stderr[-2000:]}")
        return output_path

    def mux_original_audio(self, video: str | Path, source_with_audio: str | Path, output: str | Path) -> Path:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            self._binary(self.ffmpeg), "-y",
            "-i", str(video),
            "-i", str(source_with_audio),
            "-map", "0:v:0",
            "-map", "1:a?",
            "-c:v", "copy",
            "-c:a", "copy",
            "-shortest",
            str(output_path),
        ]
        proc = subprocess.run(command, text=True, capture_output=True, check=False)
        if proc.returncode != 0:
            raise MediaError(f"audio mux failed: {proc.stderr[-2000:]}")
        return output_path
