from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from collections.abc import Sequence

import cv2
import numpy as np

from app.models.enums import ReconstructionQuality


class EraserRoute(str, Enum):
    CLASSICAL = "classical"
    TEMPORAL_PLUGIN = "temporal_plugin"
    REVIEW = "review"


@dataclass(frozen=True, slots=True)
class EraserRegionFeatures:
    texture_score: float
    motion_score: float
    classical_confidence: float
    protected_overlap: float


class EraserRouter:
    def __init__(
        self,
        *,
        max_protected_overlap: float = 0.12,
        texture_threshold: float = 90.0,
        motion_threshold: float = 8.0,
        low_classical_confidence: float = 0.30,
    ) -> None:
        self.max_protected_overlap = max_protected_overlap
        self.texture_threshold = texture_threshold
        self.motion_threshold = motion_threshold
        self.low_classical_confidence = low_classical_confidence

    def select(self, features: EraserRegionFeatures, *, plugin_available: bool) -> EraserRoute:
        if features.protected_overlap > self.max_protected_overlap:
            return EraserRoute.REVIEW
        if not plugin_available:
            return EraserRoute.CLASSICAL
        difficult_texture_motion = (
            features.texture_score >= self.texture_threshold
            and features.motion_score >= self.motion_threshold
        )
        if difficult_texture_motion or features.classical_confidence < self.low_classical_confidence:
            return EraserRoute.TEMPORAL_PLUGIN
        return EraserRoute.CLASSICAL


def analyze_region_features(
    frame: np.ndarray,
    previous_frame: np.ndarray | None,
    mask: np.ndarray,
    protected_mask: np.ndarray,
    quality: ReconstructionQuality,
) -> EraserRegionFeatures:
    hard = mask > 0
    if not np.any(hard):
        return EraserRegionFeatures(0.0, 0.0, 1.0, 0.0)
    ys, xs = np.nonzero(hard)
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    texture = float(cv2.Laplacian(gray[y0:y1, x0:x1], cv2.CV_32F).var())
    if previous_frame is None:
        motion = 0.0
    else:
        delta = np.abs(frame.astype(np.float32) - previous_frame.astype(np.float32)).mean(axis=2)
        motion = float(delta[hard].mean())
    overlap = float(np.count_nonzero(hard & (protected_mask > 0)) / max(np.count_nonzero(hard), 1))
    confidence = {
        ReconstructionQuality.HIGH: 1.0,
        ReconstructionQuality.MEDIUM: 0.6,
        ReconstructionQuality.LOW: 0.1,
        ReconstructionQuality.FAILED: 0.0,
    }[quality]
    return EraserRegionFeatures(texture, motion, confidence, overlap)


class HybridEraser:
    """Run the classical path, then route demonstrably difficult regions to a temporal plugin.

    Provider output is never trusted as a full-frame replacement: only the effective stroke mask
    is composited back onto the source frame.
    """

    def __init__(self, *, classical, plugin, router: EraserRouter | None = None) -> None:
        self.classical = classical
        self.plugin = plugin
        self.router = router or EraserRouter()

    def process(
        self,
        *,
        frames: Sequence[np.ndarray],
        subtitle_masks: Sequence[np.ndarray],
        protected_masks: Sequence[np.ndarray],
        scene_ids: Sequence[int],
        fps: float = 24.0,
        fp16: bool = False,
    ):
        from app.core.eraser.inpainting_provider import InpaintingContext
        from app.core.eraser.pipeline import EraserBatchResult
        from app.core.eraser.reconstruction import compose_inside_mask

        classical_result = self.classical.process(
            frames=frames,
            subtitle_masks=subtitle_masks,
            protected_masks=protected_masks,
            scene_ids=scene_ids,
        )
        plugin_masks = [np.zeros_like(mask, dtype=np.uint8) for mask in subtitle_masks]
        routed: list[int] = []
        for index, effective_mask in enumerate(classical_result.effective_masks):
            if not np.any(effective_mask):
                continue
            previous = frames[index - 1] if index > 0 and scene_ids[index - 1] == scene_ids[index] else None
            features = analyze_region_features(
                frames[index],
                previous,
                effective_mask,
                protected_masks[index],
                classical_result.qualities[index],
            )
            route = self.router.select(features, plugin_available=True)
            if route is EraserRoute.TEMPORAL_PLUGIN:
                plugin_masks[index] = effective_mask.copy()
                routed.append(index)

        if not routed:
            return classical_result

        plugin_result = self.plugin.inpaint(
            list(frames),
            plugin_masks,
            InpaintingContext(fps=fps, fp16=fp16),
        )
        if len(plugin_result.frames) != len(frames):
            raise ValueError("temporal plugin returned an unexpected frame count")

        output_frames = list(classical_result.frames)
        qualities = list(classical_result.qualities)
        sources = list(classical_result.reconstruction_sources)
        review = set(classical_result.review_frames)
        for index in routed:
            mask = plugin_masks[index]
            output_frames[index] = compose_inside_mask(
                frames[index], plugin_result.frames[index], mask, feather=2
            )
            qualities[index] = ReconstructionQuality.MEDIUM
            sources[index] = f"plugin:{plugin_result.provider_name}"
            review.discard(index)

        return EraserBatchResult(
            frames=tuple(output_frames),
            qualities=tuple(qualities),
            reconstruction_sources=tuple(sources),
            review_frames=tuple(sorted(review)),
            effective_masks=classical_result.effective_masks,
        )
