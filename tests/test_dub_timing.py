"""Ep giong Viet vua khung thoi gian cua phu de goc.

atempo cua ffmpeg nhan 0.5-100 trong mot tang, nhung vuot 2x mot lan thi
meo tieng ro. Chuoi nhieu tang giu moi tang trong [0.5, 2.0] ma tich van
bang dung tempo yeu cau.
"""
from __future__ import annotations

import math

import pytest

from app.core.dubbing.timing import (
    TEMPO_MAX,
    TEMPO_MIN,
    atempo_chain,
    atempo_filter,
    fit_tempo,
)


def test_fit_tempo_is_ratio_of_natural_to_window():
    assert fit_tempo(3000, 1500) == pytest.approx(2.0)
    assert fit_tempo(750, 1500) == pytest.approx(0.5)


@pytest.mark.parametrize("natural_ms,window_ms", [(0, 1000), (-1, 1000), (1000, 0), (1000, -5)])
def test_fit_tempo_rejects_non_positive(natural_ms, window_ms):
    with pytest.raises(ValueError):
        fit_tempo(natural_ms, window_ms)


def test_unity_tempo_needs_no_filter():
    assert atempo_chain(1.0) == ()
    assert atempo_filter(1.0) == ""


def test_tempo_inside_safe_range_uses_one_stage():
    assert atempo_chain(1.8) == pytest.approx((1.8,))
    assert atempo_chain(0.5) == pytest.approx((0.5,))
    assert atempo_chain(2.0) == pytest.approx((2.0,))


def test_fast_tempo_splits_into_two_stages():
    stages = atempo_chain(2.33)
    assert len(stages) == 2
    assert math.prod(stages) == pytest.approx(2.33)


def test_slow_tempo_splits_into_two_stages():
    stages = atempo_chain(0.3)
    assert len(stages) == 2
    assert math.prod(stages) == pytest.approx(0.3)


def test_very_fast_tempo_splits_into_three_stages():
    stages = atempo_chain(5.0)
    assert len(stages) == 3
    assert math.prod(stages) == pytest.approx(5.0)


@pytest.mark.parametrize(
    "tempo",
    [0.12, 0.25, 0.3, 0.49, 0.5, 0.9, 1.1, 1.8, 2.0, 2.01, 2.33, 4.0, 5.0, 9.9],
)
def test_every_stage_stays_in_ffmpeg_safe_range(tempo):
    stages = atempo_chain(tempo)
    assert stages, "non-unity tempo must produce at least one stage"
    assert all(TEMPO_MIN <= stage <= TEMPO_MAX for stage in stages), stages
    assert math.prod(stages) == pytest.approx(tempo)


def test_atempo_filter_joins_stages_for_ffmpeg():
    assert atempo_filter(1.8) == "atempo=1.800000"
    assert atempo_filter(4.0) == "atempo=2.000000,atempo=2.000000"


@pytest.mark.parametrize("tempo", [0.0, -1.0])
def test_atempo_chain_rejects_non_positive(tempo):
    with pytest.raises(ValueError):
        atempo_chain(tempo)
