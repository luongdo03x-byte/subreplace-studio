from fractions import Fraction
import pytest
from app.core.subtitle_overlay.band import BandResult
from app.core.subtitle_overlay.layout import lock_layout, batch_profile


def test_locked_height_and_manual_override():
    band = BandResult(1000., 240, 300, ())
    auto = lock_layout(band, (1920, 1080), 60)
    assert (auto.y, auto.extra_height) == (1009, 71)
    manual = lock_layout(band, (1920, 1080), 60, manual_y=1080)
    assert (manual.y, manual.extra_height) == (1080, 142)
    profile = batch_profile(((1920, 1080, auto), (720, 1080, manual)), Fraction(25), True)
    assert (profile.width, profile.height) == (1920, 1222)
    assert auto.extra_height == 71


def test_fallback_stays_locked_and_negative_manual_y_rejected():
    band = BandResult(None, 0, 300, ())
    layout = lock_layout(band, (720, 1280), 60)
    assert layout.fallback
    assert layout.y == 1127
    with pytest.raises(ValueError):
        lock_layout(band, (720, 1280), 60, -1)
