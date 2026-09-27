"""Fit synthesized Vietnamese speech into the source subtitle's time window."""
from __future__ import annotations

import math
import numpy as np


def trim_speech_padding(samples, sample_rate):
    """Remove service silence, retaining a 40ms margin around audible speech."""
    level = np.abs(samples.astype(np.float64))
    audible = np.flatnonzero(level > max(32, float(level.max(initial=0)) * .01))
    if not len(audible):
        raise ValueError('Speech service returned silent audio')
    margin = round(sample_rate * .04)
    return samples[max(0, int(audible[0]) - margin):min(len(samples), int(audible[-1]) + margin + 1)]

# ffmpeg's atempo accepts 0.5-100 in a single stage, but anything past 2x in
# one pass smears transients audibly. Chaining stages of tempo**(1/n) keeps the
# same overall factor with far less artifacting.
TEMPO_MIN = 0.5
TEMPO_MAX = 2.0
TEMPO_EPSILON = 1e-3


def fit_tempo(natural_ms: int, window_ms: int) -> float:
    """Tempo factor that squeezes natural speech into the subtitle window."""
    if natural_ms <= 0:
        raise ValueError("natural_ms must be positive")
    if window_ms <= 0:
        raise ValueError("window_ms must be positive")
    return float(natural_ms) / float(window_ms)


def atempo_chain(tempo: float) -> tuple[float, ...]:
    """Split a tempo factor into stages that each stay within ffmpeg's sweet spot."""
    if tempo <= 0:
        raise ValueError("tempo must be positive")
    if abs(tempo - 1.0) < TEMPO_EPSILON:
        return ()
    if TEMPO_MIN <= tempo <= TEMPO_MAX:
        return (float(tempo),)
    reach = tempo if tempo > TEMPO_MAX else 1.0 / tempo
    stages = max(2, math.ceil(math.log2(reach)))
    factor = tempo ** (1.0 / stages)
    return tuple([factor] * stages)


def atempo_filter(tempo: float) -> str:
    """ffmpeg filter fragment for a tempo factor, or "" when no change is needed."""
    return ",".join(f"atempo={stage:.6f}" for stage in atempo_chain(tempo))
