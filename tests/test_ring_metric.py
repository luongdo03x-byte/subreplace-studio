"""ring_mae_robust must tolerate stochastic background shimmer.

On the bead-curtain background (test_60s f681-696) every reconstruction was
rejected: ring_mae(raw) > 18 even for perfectly aligned references because
bead sparkle differs frame-to-frame. The robust metric blurs before the
MAE so shimmer cancels while genuine misalignment still fails. Gate
thresholds (8/18) are unchanged.
"""
import numpy as np

from app.core.eraser.temporal_qa import ring_mae, ring_mae_robust


def _scene(shift=0, seed=0):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:256, 0:256]
    base = np.stack([
        120 + 60 * np.sin(xx / 9.0 + shift / 5.0),
        100 + 50 * np.sin(yy / 11.0),
        90 + 40 * np.sin((xx + yy) / 13.0),
    ], axis=-1)
    sparkle = (rng.random((256, 256, 1)) > 0.92) * rng.integers(80, 255, (256, 256, 1))
    img = np.clip(base + sparkle, 0, 255).astype(np.uint8)
    if shift:
        img = np.roll(img, shift, axis=1)
    return img


MASK = np.zeros((256, 256), np.uint8)
MASK[100:150, 100:160] = 255


def test_perfect_alignment_with_shimmer_passes():
    target = _scene(shift=0, seed=1)
    reference = _scene(shift=0, seed=2)  # same structure, different sparkle
    raw = ring_mae(reference, target, MASK)
    robust = ring_mae_robust(reference, target, MASK)
    assert raw > 18, f"raw metric should have rejected this before the fix: {raw}"
    assert robust <= 8, f"perfect alignment must pass: robust={robust}"


def test_real_misalignment_still_fails():
    target = _scene(shift=0, seed=3)
    reference = _scene(shift=10, seed=3)  # structure displaced by 10 px
    robust = ring_mae_robust(reference, target, MASK)
    assert robust > 18, f"misalignment must still fail: robust={robust}"


def test_identical_images_zero():
    img = _scene(shift=0, seed=4)
    assert ring_mae_robust(img, img, MASK) == 0.0
