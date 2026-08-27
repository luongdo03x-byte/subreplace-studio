from __future__ import annotations

from app.models.quality import QualityGateResult, QualityMetrics


class QualityGate:
    def evaluate(self, metrics: QualityMetrics) -> QualityGateResult:
        failures: list[str] = []
        checks = (
            (metrics.outside_mask_changed_pixels == 0, "outside_mask_preservation"),
            (metrics.watermark_mae <= 0.5, "watermark_preservation"),
            (metrics.uniform_rectangle_score <= 0.30, "no_uniform_rectangle"),
            (metrics.residual_text_energy <= 0.25, "residual_text_energy"),
            (metrics.temporal_flicker <= 1.80, "temporal_flicker"),
            (metrics.reconstruction_psnr_mean >= 26.0, "reconstruction_psnr_mean"),
            (metrics.reconstruction_psnr_worst >= 20.0, "reconstruction_psnr_worst"),
        )
        for ok, name in checks:
            if not ok:
                failures.append(name)
        return QualityGateResult(not failures, tuple(failures), metrics)
