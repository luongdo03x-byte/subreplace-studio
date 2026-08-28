from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
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

    @staticmethod
    def _run_cancellable(command: list[str], *, cancel_event=None) -> subprocess.CompletedProcess[str]:
        if cancel_event is not None and cancel_event.is_set():
            raise MediaError("media operation cancelled")
        process = subprocess.Popen(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        while True:
            try:
                stdout, stderr = process.communicate(timeout=0.2)
                if cancel_event is not None and cancel_event.is_set():
                    raise MediaError("media operation cancelled")
                return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                if cancel_event is not None and cancel_event.is_set():
                    process.terminate()
                    try:
                        stdout, stderr = process.communicate(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        stdout, stderr = process.communicate()
                    raise MediaError(f"media operation cancelled: {stderr[-1000:]}")

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

    def concat(self, inputs: list[str | Path], output: str | Path, *, cancel_event=None) -> Path:
        sources = [Path(item).resolve() for item in inputs]
        if len(sources) < 2:
            raise MediaError("at least two videos are required for concatenation")
        metadata = [self.probe(source) for source in sources]
        output_path = Path(output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        width = metadata[0].width + metadata[0].width % 2
        height = metadata[0].height + metadata[0].height % 2
        fps = metadata[0].fps if metadata[0].fps > 0 else 25.0
        video_filter = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
            f"fps={fps:.6f},format=yuv420p"
        )
        temporary_output = output_path.with_name(f".{output_path.stem}.concat{output_path.suffix}")
        ffmpeg = self._binary(self.ffmpeg)
        try:
            with tempfile.TemporaryDirectory(prefix="subreplace-concat-") as tmp:
                temp_dir = Path(tmp)
                normalized: list[Path] = []
                for index, (source, meta) in enumerate(zip(sources, metadata, strict=True)):
                    target = temp_dir / f"clip-{index:04d}.mp4"
                    command = [ffmpeg, "-y", "-i", str(source)]
                    if meta.has_audio:
                        command += ["-map", "0:v:0", "-map", "0:a:0"]
                        audio_filter = "aresample=48000,apad"
                    else:
                        command += [
                            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                            "-map", "0:v:0", "-map", "1:a:0",
                        ]
                        audio_filter = "aresample=48000"
                    command += [
                        "-vf", video_filter,
                        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                        "-af", audio_filter, "-c:a", "aac", "-ar", "48000", "-ac", "2",
                        "-t", f"{max(meta.duration_ms, 1) / 1000.0:.3f}",
                        str(target),
                    ]
                    proc = self._run_cancellable(command, cancel_event=cancel_event)
                    if proc.returncode != 0:
                        raise MediaError(f"video normalization failed for {source}: {proc.stderr[-2000:]}")
                    normalized.append(target)
                concat_list = temp_dir / "concat.txt"
                concat_list.write_text(
                    "".join(f"file '{path.as_posix()}'\n" for path in normalized), encoding="utf-8"
                )
                command = [
                    ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
                    "-c", "copy", "-movflags", "+faststart", str(temporary_output),
                ]
                proc = self._run_cancellable(command, cancel_event=cancel_event)
                if proc.returncode != 0:
                    raise MediaError(f"video concatenation failed: {proc.stderr[-2000:]}")
            if not temporary_output.is_file() or temporary_output.stat().st_size == 0:
                raise MediaError("video concatenation produced an empty output")
            self.probe(temporary_output)
            if cancel_event is not None and cancel_event.is_set():
                raise MediaError("media operation cancelled")
            temporary_output.replace(output_path)
            return output_path
        finally:
            temporary_output.unlink(missing_ok=True)
