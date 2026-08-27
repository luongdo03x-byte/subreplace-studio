from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class JobRecord:
    id: str
    stage: str
    status: JobStatus
    attempts: int
    progress: float
    created_at: str
    updated_at: str
    error: str | None = None
    completed_stages: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "stage": self.stage,
            "status": self.status.value,
            "attempts": self.attempts,
            "progress": self.progress,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
            "completed_stages": list(self.completed_stages),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "JobRecord":
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError("job metadata must be an object")
        completed = payload.get("completed_stages", [])
        if not isinstance(completed, list) or not all(isinstance(item, str) for item in completed):
            raise ValueError("completed_stages must be a list of strings")
        return cls(
            id=str(payload.get("id") or ""),
            stage=str(payload.get("stage") or ""),
            status=JobStatus(str(payload.get("status"))),
            attempts=int(payload.get("attempts", 0)),
            progress=float(payload.get("progress", 0.0)),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
            error=str(payload["error"]) if payload.get("error") is not None else None,
            completed_stages=tuple(completed),
            metadata=dict(metadata),
        )
