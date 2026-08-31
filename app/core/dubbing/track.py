"""Assemble per-line speech clips into one narration track."""
from __future__ import annotations

import wave
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

FADE_MS = 5


@dataclass(frozen=True, slots=True)
class TrackSegment:
    start_ms: int
    end_ms: int
    samples: np.ndarray


def _fit_window(samples: np.ndarray, window_samples: int) -> np.ndarray:
    """Trim or pad to exactly the window length.

    atempo lands a few milliseconds off its target, so this is where the
    absolute-fit guarantee is actually enforced.
    """
    if len(samples) >= window_samples:
        return samples[:window_samples].astype(np.int16)
    padded = np.zeros(window_samples, dtype=np.int16)
    padded[: len(samples)] = samples
    return padded


def _apply_fade(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    fade = min(int(sample_rate * FADE_MS / 1000), len(samples) // 2)
    if fade <= 0:
        return samples
    ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
    faded = samples.astype(np.float32)
    faded[:fade] *= ramp
    faded[-fade:] *= ramp[::-1]
    return faded.astype(np.int16)


def build_track(
    segments: Sequence[TrackSegment], *, total_ms: int, sample_rate: int
) -> np.ndarray:
    """Silent track of the video's length with each line placed at its own window."""
    total_samples = max(0, int(round(total_ms * sample_rate / 1000)))
    track = np.zeros(total_samples, dtype=np.int16)
    ordered = sorted(segments, key=lambda item: item.start_ms)
    for index, segment in enumerate(ordered):
        end_ms = segment.end_ms
        if index + 1 < len(ordered):
            # coalesce_dialogue_events already merges overlapping cues, but a
            # stray overlap must never let one line bleed over the next.
            end_ms = min(end_ms, ordered[index + 1].start_ms)
        start = max(0, min(total_samples, int(round(segment.start_ms * sample_rate / 1000))))
        stop = max(start, min(total_samples, int(round(end_ms * sample_rate / 1000))))
        if stop <= start:
            continue
        track[start:stop] = _apply_fade(_fit_window(segment.samples, stop - start), sample_rate)
    return track


def write_wav(path: str | Path, track: np.ndarray, *, sample_rate: int) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(track.astype("<i2").tobytes())
    return output
