from __future__ import annotations


def sync_target_position(master_ms: int, follower_ms: int, *, tolerance_ms: int = 80) -> int | None:
    """Return a correction position only when preview players drift meaningfully."""
    if tolerance_ms < 0:
        raise ValueError("tolerance_ms must be non-negative")
    if abs(int(master_ms) - int(follower_ms)) <= tolerance_ms:
        return None
    return max(0, int(master_ms))
