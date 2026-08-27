from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def find_clean_reference_indices(
    *,
    target_index: int,
    occupancy: Sequence[np.ndarray],
    scene_ids: Sequence[int],
    max_references: int = 5,
) -> list[int]:
    scene = scene_ids[target_index]
    candidates = [
        i
        for i, mask in enumerate(occupancy)
        if i != target_index and scene_ids[i] == scene and not np.any(mask)
    ]
    candidates.sort(key=lambda i: (abs(i - target_index), i))
    return candidates[:max_references]


def temporal_propagation_order(
    occupied: Sequence[bool], scene_ids: Sequence[int]
) -> list[int]:
    remaining = {i for i, value in enumerate(occupied) if value}
    clean = {i for i, value in enumerate(occupied) if not value}
    order: list[int] = []
    while remaining:
        ranked: list[tuple[int, int]] = []
        for i in remaining:
            distances = [abs(i - j) for j in clean if scene_ids[j] == scene_ids[i]]
            depth = min(distances) if distances else 10**9
            ranked.append((depth, i))
        ranked.sort()
        min_depth = ranked[0][0]
        layer = [i for depth, i in ranked if depth == min_depth]
        # Deterministic outside-in order naturally emerges from the distance rank.
        for i in layer:
            order.append(i)
            clean.add(i)
            remaining.remove(i)
    return order
