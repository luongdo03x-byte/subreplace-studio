"""Phan giong nam/nu bang cao do giong goc, khong dung model nao.

Nam ~85-155Hz, nu ~165-255Hz. Vung 155-190Hz la cho giong nu tram va giong
nam cao chong nhau: doan bua o do cho ket qua lat qua lat lai giua cac cau
lien tiep, kho chiu hon han so voi roi ve mot giong on dinh.
"""
from __future__ import annotations

import wave

import numpy as np
import pytest

from app.core.dubbing.voice import (
    FEMALE_MIN_HZ,
    MALE_MAX_HZ,
    choose_gender,
    estimate_f0,
    read_slice,
)

RATE = 16000


def _write_wav(path, samples):
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(samples.astype("<i2").tobytes())
    return path


def _tone(freq, *, duration_s=1.0, amplitude=8000):
    t = np.arange(int(RATE * duration_s), dtype=np.float64) / RATE
    return amplitude * np.sin(2 * np.pi * freq * t)


def test_male_pitch_maps_to_male_voice(tmp_path):
    path = _write_wav(tmp_path / "male.wav", _tone(120.0))
    samples, rate = read_slice(path, 0, 1000)
    f0 = estimate_f0(samples, rate)
    assert f0 == pytest.approx(120.0, rel=0.05)
    assert choose_gender(f0) == "male"


def test_female_pitch_maps_to_female_voice(tmp_path):
    path = _write_wav(tmp_path / "female.wav", _tone(220.0))
    samples, rate = read_slice(path, 0, 1000)
    f0 = estimate_f0(samples, rate)
    assert f0 == pytest.approx(220.0, rel=0.05)
    assert choose_gender(f0) == "female"


def test_dead_band_pitch_falls_back_to_default(tmp_path):
    path = _write_wav(tmp_path / "ambiguous.wav", _tone(170.0))
    samples, rate = read_slice(path, 0, 1000)
    f0 = estimate_f0(samples, rate)
    assert MALE_MAX_HZ <= f0 <= FEMALE_MIN_HZ
    assert choose_gender(f0) == "default"


def test_silence_yields_no_pitch(tmp_path):
    path = _write_wav(tmp_path / "silence.wav", np.zeros(RATE))
    samples, rate = read_slice(path, 0, 1000)
    assert estimate_f0(samples, rate) == 0.0
    assert choose_gender(0.0) == "default"


def test_white_noise_is_not_mistaken_for_speech(tmp_path):
    rng = np.random.default_rng(0)
    noise = rng.normal(0.0, 3000.0, RATE)
    path = _write_wav(tmp_path / "noise.wav", noise)
    samples, rate = read_slice(path, 0, 1000)
    assert estimate_f0(samples, rate) == 0.0
    assert choose_gender(0.0) == "default"


def test_read_slice_extracts_only_the_requested_window(tmp_path):
    path = _write_wav(tmp_path / "long.wav", _tone(120.0, duration_s=3.0))
    samples, rate = read_slice(path, 1000, 2000)
    assert rate == RATE
    assert len(samples) == RATE


def test_read_slice_clamps_past_end_of_file(tmp_path):
    path = _write_wav(tmp_path / "short.wav", _tone(120.0, duration_s=0.5))
    samples, _ = read_slice(path, 0, 5000)
    assert len(samples) == RATE // 2


def test_read_slice_downmixes_stereo(tmp_path):
    path = tmp_path / "stereo.wav"
    mono = _tone(120.0).astype("<i2")
    stereo = np.repeat(mono, 2)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(stereo.tobytes())
    samples, rate = read_slice(path, 0, 1000)
    assert len(samples) == RATE
    assert estimate_f0(samples, rate) == pytest.approx(120.0, rel=0.05)


@pytest.mark.parametrize(
    "f0,expected",
    [(90.0, "male"), (154.9, "male"), (155.0, "default"), (190.0, "default"),
     (190.1, "female"), (250.0, "female"), (0.0, "default")],
)
def test_gender_boundaries(f0, expected):
    assert choose_gender(f0) == expected
