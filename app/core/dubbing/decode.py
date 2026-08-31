"""Turn encoded speech into PCM and stretch it to fit a subtitle window.

The command builders are pure so the whole audio path can be tested without
ffmpeg installed; only decode_to_pcm/stretch_pcm actually spawn a process.
"""
from __future__ import annotations

import shutil
import subprocess

import numpy as np

from .timing import atempo_filter


class DecodeError(RuntimeError):
    pass


def _check_sample_rate(sample_rate: int) -> None:
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")


def build_decode_command(*, sample_rate: int, ffmpeg: str = "ffmpeg") -> list[str]:
    _check_sample_rate(sample_rate)
    return [
        ffmpeg, "-hide_banner", "-loglevel", "error",
        "-i", "pipe:0",
        "-vn", "-ar", str(sample_rate), "-ac", "1",
        "-f", "s16le", "pipe:1",
    ]


def build_stretch_command(*, tempo: float, sample_rate: int, ffmpeg: str = "ffmpeg") -> list[str]:
    _check_sample_rate(sample_rate)
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error",
        "-f", "s16le", "-ar", str(sample_rate), "-ac", "1",
        "-i", "pipe:0",
    ]
    filters = atempo_filter(tempo)
    if filters:
        command += ["-filter:a", filters]
    command += ["-ar", str(sample_rate), "-ac", "1", "-f", "s16le", "pipe:1"]
    return command


def _run(command: list[str], payload: bytes) -> np.ndarray:
    binary = shutil.which(command[0])
    if binary is None:
        raise DecodeError(f"required media binary is not installed: {command[0]}")
    proc = subprocess.run([binary, *command[1:]], input=payload, capture_output=True, check=False)
    if proc.returncode != 0:
        raise DecodeError(f"ffmpeg audio conversion failed: {proc.stderr[-2000:].decode('utf-8', 'replace')}")
    return np.frombuffer(proc.stdout, dtype="<i2").astype(np.int16)


def decode_to_pcm(audio: bytes, *, sample_rate: int, ffmpeg: str = "ffmpeg") -> np.ndarray:
    return _run(build_decode_command(sample_rate=sample_rate, ffmpeg=ffmpeg), audio)


def stretch_pcm(samples: np.ndarray, *, tempo: float, sample_rate: int, ffmpeg: str = "ffmpeg") -> np.ndarray:
    if not atempo_filter(tempo):
        return samples.astype(np.int16)
    payload = samples.astype("<i2").tobytes()
    return _run(build_stretch_command(tempo=tempo, sample_rate=sample_rate, ffmpeg=ffmpeg), payload)


class PcmCodec:
    """Injectable bundle so the synthesis stage can be tested without ffmpeg."""

    def __init__(self, *, ffmpeg: str = "ffmpeg") -> None:
        self.ffmpeg = ffmpeg

    def decode(self, audio: bytes, *, sample_rate: int) -> np.ndarray:
        return decode_to_pcm(audio, sample_rate=sample_rate, ffmpeg=self.ffmpeg)

    def stretch(self, samples: np.ndarray, *, tempo: float, sample_rate: int) -> np.ndarray:
        return stretch_pcm(samples, tempo=tempo, sample_rate=sample_rate, ffmpeg=self.ffmpeg)
