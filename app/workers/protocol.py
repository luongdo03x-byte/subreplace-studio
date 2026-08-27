from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from typing import Any, Mapping


class WorkerEventType(str, Enum):
    STARTED = "started"
    PROGRESS = "progress"
    COMPLETED = "completed"
    FAILED = "failed"
    LOG = "log"


@dataclass(frozen=True, slots=True)
class WorkerCommand:
    job_id: str
    stage: str
    project_path: str
    config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.job_id.strip():
            raise ValueError("job_id is required")
        if not self.stage.strip():
            raise ValueError("stage is required")
        if not self.project_path.strip():
            raise ValueError("project_path is required")
        if not isinstance(self.config, dict):
            raise ValueError("worker config must be an object")

    def to_json(self) -> str:
        return json.dumps(
            {
                "job_id": self.job_id,
                "stage": self.stage,
                "project_path": self.project_path,
                "config": self.config,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, raw: str) -> "WorkerCommand":
        payload = json.loads(raw)
        if not isinstance(payload, Mapping):
            raise ValueError("worker command must be a JSON object")
        config = payload.get("config", {})
        if not isinstance(config, dict):
            raise ValueError("worker config must be an object")
        return cls(
            job_id=str(payload.get("job_id") or ""),
            stage=str(payload.get("stage") or ""),
            project_path=str(payload.get("project_path") or ""),
            config=dict(config),
        )


@dataclass(frozen=True, slots=True)
class WorkerEvent:
    type: WorkerEventType
    job_id: str
    stage: str
    progress: float
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.progress) <= 1.0:
            raise ValueError("worker progress must be between 0 and 1")
        if not isinstance(self.data, dict):
            raise ValueError("worker event data must be an object")

    def to_json(self) -> str:
        return json.dumps(
            {
                "type": self.type.value,
                "job_id": self.job_id,
                "stage": self.stage,
                "progress": float(self.progress),
                "message": self.message,
                "data": self.data,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, raw: str) -> "WorkerEvent":
        payload = json.loads(raw)
        if not isinstance(payload, Mapping):
            raise ValueError("worker event must be a JSON object")
        raw_type = payload.get("type")
        try:
            event_type = WorkerEventType(str(raw_type))
        except ValueError as exc:
            raise ValueError(f"unknown worker event type: {raw_type}") from exc
        data = payload.get("data", {})
        if not isinstance(data, dict):
            raise ValueError("worker event data must be an object")
        return cls(
            event_type,
            str(payload.get("job_id") or ""),
            str(payload.get("stage") or ""),
            float(payload.get("progress", 0.0)),
            str(payload.get("message") or ""),
            dict(data),
        )
