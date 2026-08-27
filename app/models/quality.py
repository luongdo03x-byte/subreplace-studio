from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QualityMetrics:
    outside_mask_changed_pixels: int
    watermark_mae: float
    uniform_rectangle_score: float
    residual_text_energy: float
    temporal_flicker: float
    reconstruction_psnr_mean: float
    reconstruction_psnr_worst: float


@dataclass(frozen=True, slots=True)
class QualityGateResult:
    passed: bool
    failed_metrics: tuple[str, ...]
    metrics: QualityMetrics
