"""Pick a dub voice from the pitch of the original speaker.

Autocorrelation on the already-extracted source audio is enough to separate
male from female fundamentals, so this needs no model, no download, and no
HuggingFace token. Speaker diarization would tell us who is talking but not
their vocal range, which is the only thing the voice choice depends on.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

MALE_MAX_HZ = 155.0
FEMALE_MIN_HZ = 190.0

F0_MIN_HZ = 70.0
F0_MAX_HZ = 320.0
FRAME_MS = 40
HOP_MS = 20
MIN_VOICED_FRAMES = 5
VOICED_CORRELATION = 0.3
SILENCE_RMS = 200.0


def read_slice(path: str | Path, start_ms: int, end_ms: int) -> tuple[np.ndarray, int]:
    """Read one time window of a 16-bit PCM wav as mono float samples."""
    with wave.open(str(path), "rb") as handle:
        if handle.getsampwidth() != 2:
            raise ValueError("source audio must be 16-bit PCM")
        rate = handle.getframerate()
        channels = handle.getnchannels()
        total = handle.getnframes()
        start = max(0, min(total, int(start_ms * rate / 1000)))
        end = max(start, min(total, int(end_ms * rate / 1000)))
        handle.setpos(start)
        raw = handle.readframes(end - start)
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32)
    if channels > 1:
        usable = (len(samples) // channels) * channels
        samples = samples[:usable].reshape(-1, channels).mean(axis=1)
    return samples, rate


def _frame_f0(frame: np.ndarray, sample_rate: int) -> float:
    centred = frame - frame.mean()
    if float(np.sqrt(np.mean(np.square(centred)))) < SILENCE_RMS:
        return 0.0
    correlation = np.correlate(centred, centred, mode="full")[len(centred) - 1:]
    if correlation[0] <= 0.0:
        return 0.0
    correlation = correlation / correlation[0]
    min_lag = int(sample_rate / F0_MAX_HZ)
    max_lag = int(sample_rate / F0_MIN_HZ)
    if min_lag < 1 or max_lag <= min_lag or max_lag >= len(correlation):
        return 0.0
    window = correlation[min_lag:max_lag]
    peak = int(np.argmax(window))
    # An unvoiced frame's autocorrelation decays without a clear periodic peak,
    # which is what separates speech from noise and room tone here.
    if window[peak] < VOICED_CORRELATION:
        return 0.0
    return float(sample_rate) / float(min_lag + peak)


def estimate_f0(samples: np.ndarray, sample_rate: int) -> float:
    """Median fundamental frequency over voiced frames; 0.0 when undetermined."""
    frame_length = int(sample_rate * FRAME_MS / 1000)
    hop = int(sample_rate * HOP_MS / 1000)
    if frame_length <= 0 or hop <= 0 or len(samples) < frame_length:
        return 0.0
    voiced = [
        value
        for start in range(0, len(samples) - frame_length + 1, hop)
        if (value := _frame_f0(samples[start:start + frame_length], sample_rate)) > 0.0
    ]
    if len(voiced) < MIN_VOICED_FRAMES:
        return 0.0
    return float(np.median(voiced))


def choose_gender(f0_hz: float) -> str:
    """Map a fundamental frequency to "male", "female", or "default"."""
    if f0_hz <= 0.0:
        return "default"
    if f0_hz < MALE_MAX_HZ:
        return "male"
    if f0_hz > FEMALE_MIN_HZ:
        return "female"
    return "default"
