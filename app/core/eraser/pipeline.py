from __future__ import annotations

import cv2
import os
import sys
from dataclasses import dataclass
from collections.abc import Sequence

import numpy as np

_DEBUG_ERASE = bool(os.environ.get("SUBREPLACE_ERASE_DEBUG"))

from app.models.enums import ReconstructionQuality

from .mask_refiner import subtract_protected_regions
from .motion import align_reference
from .reconstruction import compose_inside_mask, median_fusion, single_frame_inpaint
from .scene_reference import find_clean_reference_indices, temporal_propagation_order


def _text_delta(frame: np.ndarray, mask: np.ndarray) -> float:
    """Ratio of high-pass energy inside the mask versus its surround.

    Burned-in glyph edges dominate the masked area's high-pass signal while
    a text-free region shows the same texture energy as its surround. The
    ratio is independent of absolute brightness, so it keeps working on
    bright backgrounds where a plain luminance difference reads as zero.
    """
    hard = mask > 0
    if not np.any(hard):
        return 0.0
    ring = cv2.dilate(mask, np.ones((11, 11), np.uint8)) > 0
    ring &= ~hard
    if not np.any(ring):
        return 0.0
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
    high_pass = gray - cv2.boxFilter(gray, -1, (41, 41))
    ring_energy = float(np.abs(high_pass[ring]).mean())
    return float(np.abs(high_pass[hard]).mean()) / (ring_energy + 1e-6)


def _frame_contains_text(frame: np.ndarray, mask: np.ndarray, *, delta_threshold: float = 1.6) -> bool:
    """True when the mask region still shows glyphs (high-pass residual).

    Occupancy bookkeeping can mark a frame clean while the subtitle is
    actually on screen.  Using the high-pass energy ratio detects glyphs
    regardless of scene brightness.
    """
    return _text_delta(frame, mask) > delta_threshold


@dataclass(frozen=True, slots=True)
class EraserBatchResult:
    frames: tuple[np.ndarray, ...]
    qualities: tuple[ReconstructionQuality, ...]
    reconstruction_sources: tuple[str, ...]
    review_frames: tuple[int, ...]
    effective_masks: tuple[np.ndarray, ...]


class ClassicalEraser:
    def __init__(self, max_references: int = 5, max_protected_overlap: float = 0.12) -> None:
        self.max_references = max_references
        self.max_protected_overlap = max_protected_overlap

    def process(
        self,
        *,
        frames: Sequence[np.ndarray],
        subtitle_masks: Sequence[np.ndarray],
        protected_masks: Sequence[np.ndarray],
        scene_ids: Sequence[int],
    ) -> EraserBatchResult:
        n = len(frames)
        if not (len(subtitle_masks) == len(protected_masks) == len(scene_ids) == n):
            raise ValueError("frames, masks and scene_ids must have identical length")
        cleaned = [frame.copy() for frame in frames]
        qualities = [ReconstructionQuality.HIGH if not np.any(subtitle_masks[i]) else ReconstructionQuality.LOW for i in range(n)]
        sources = ["original" if not np.any(subtitle_masks[i]) else "pending" for i in range(n)]
        effective_masks = [np.zeros_like(subtitle_masks[i], dtype=np.uint8) for i in range(n)]
        review: list[int] = []

        occupied = [bool(np.any(mask)) for mask in subtitle_masks]
        order = temporal_propagation_order(occupied, scene_ids)
        dynamic_occupancy = [mask.copy() for mask in subtitle_masks]

        for index in order:
            decision = subtract_protected_regions(
                subtitle_masks[index],
                protected_masks[index],
                max_protected_overlap=self.max_protected_overlap,
                protection_margin=2,
            )
            effective_masks[index] = decision.eraser_mask
            if decision.needs_review:
                review.append(index)
                sources[index] = "protected_collision"
                qualities[index] = ReconstructionQuality.LOW
                continue
            mask = decision.eraser_mask
            if not np.any(mask):
                dynamic_occupancy[index][:] = 0
                qualities[index] = ReconstructionQuality.HIGH
                sources[index] = "no_effective_mask"
                continue

            ref_indices = find_clean_reference_indices(
                target_index=index,
                occupancy=dynamic_occupancy,
                scene_ids=scene_ids,
                max_references=self.max_references,
            )
            ref_indices = [
                r for r in ref_indices
                if not _frame_contains_text(frames[r], mask)
            ]
            candidates: list[tuple[float, np.ndarray, str]] = []
            for ref_index in ref_indices:
                aligned, ring_error, method = align_reference(cleaned[ref_index], frames[index], mask)
                candidates.append((ring_error, aligned, method))
            candidates.sort(key=lambda item: item[0])

            if candidates:
                best = candidates[: self.max_references]
                generated = median_fusion([item[1] for item in best])
                best_ring = best[0][0]
                source = "multi_reference:" + "+".join(item[2] for item in best)
            else:
                generated = single_frame_inpaint(frames[index], mask)
                best_ring = 999.0
                source = "classical_inpaint"

            result = compose_inside_mask(frames[index], generated, mask, feather=2)
            cleaned[index] = result
            sources[index] = source
            if _DEBUG_ERASE:
                ref_ids = [r for r in ref_indices]
                print(
                    f"[erase] frame={index} ring={best_ring:.1f} "
                    f"refs={ref_ids} src={source}",
                    file=sys.stderr, flush=True,
                )
            if best_ring <= 8.0:
                qualities[index] = ReconstructionQuality.HIGH
                dynamic_occupancy[index][:] = 0
            elif best_ring <= 18.0:
                qualities[index] = ReconstructionQuality.MEDIUM
                dynamic_occupancy[index][:] = 0
            elif (
                (result_delta := _text_delta(result, mask)) < 1.25
                or result_delta <= 0.5 * _text_delta(frames[index], mask)
            ):
                # Distant references mismatch the moving surround (high ring
                # error) while still erasing the glyphs cleanly. The actual
                # goal is a text-free region; accept when the composition
                # verifiably reads as background.
                qualities[index] = ReconstructionQuality.MEDIUM
                dynamic_occupancy[index][:] = 0
                sources[index] = source + "|ring_rejected_text_cleared"
            else:
                fallback = compose_inside_mask(
                    frames[index], single_frame_inpaint(frames[index], mask), mask, feather=2
                )
                fallback_delta = _text_delta(fallback, mask)
                source_delta = _text_delta(frames[index], mask)
                if candidates and (fallback_delta < 1.25 or fallback_delta <= 0.5 * source_delta):
                    # A mismatched temporal reference can fail on a moving
                    # scene even when local inpainting removes the glyph.
                    cleaned[index] = fallback
                    qualities[index] = ReconstructionQuality.MEDIUM
                    dynamic_occupancy[index][:] = 0
                    sources[index] = "classical_inpaint|temporal_fallback_text_cleared"
                else:
                    # Fail honestly: do not propagate a poor reconstruction.
                    cleaned[index] = frames[index].copy()
                    qualities[index] = ReconstructionQuality.LOW
                    sources[index] = "failed_preserved_original"
                    review.append(index)

        return EraserBatchResult(
            frames=tuple(cleaned),
            qualities=tuple(qualities),
            reconstruction_sources=tuple(sources),
            review_frames=tuple(sorted(set(review))),
            effective_masks=tuple(effective_masks),
        )
