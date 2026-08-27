from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid
from typing import Any

from .models import JobRecord, JobStatus

_JOB_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def create(
        self,
        *,
        stage: str,
        job_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> JobRecord:
        identifier = job_id or uuid.uuid4().hex
        self._validate_id(identifier)
        if not stage.strip():
            raise ValueError("job stage is required")
        path = self.path(identifier)
        if path.exists():
            raise FileExistsError(path)
        now = _now()
        record = JobRecord(
            id=identifier,
            stage=stage,
            status=JobStatus.PENDING,
            attempts=1,
            progress=0.0,
            created_at=now,
            updated_at=now,
            metadata=dict(metadata or {}),
        )
        return self._save(record)

    def path(self, job_id: str) -> Path:
        self._validate_id(job_id)
        return self.root / f"{job_id}.json"

    def load(self, job_id: str) -> JobRecord:
        path = self.path(job_id)
        if not path.is_file():
            raise FileNotFoundError(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("job record must be an object")
        return JobRecord.from_dict(payload)

    def begin_stage(self, job_id: str, stage: str) -> JobRecord:
        if not stage.strip():
            raise ValueError("job stage is required")
        record = self.load(job_id)
        return self._save(
            replace(record, stage=stage, status=JobStatus.RUNNING, error=None, updated_at=_now())
        )

    def update_progress(self, job_id: str, progress: float) -> JobRecord:
        if not 0.0 <= float(progress) <= 1.0:
            raise ValueError("job progress must be between 0 and 1")
        record = self.load(job_id)
        return self._save(replace(record, progress=float(progress), updated_at=_now()))

    def complete_stage(self, job_id: str, stage: str) -> JobRecord:
        record = self.load(job_id)
        completed = list(record.completed_stages)
        if stage not in completed:
            completed.append(stage)
        return self._save(
            replace(
                record,
                stage=stage,
                status=JobStatus.RUNNING,
                completed_stages=tuple(completed),
                error=None,
                updated_at=_now(),
            )
        )

    def fail(self, job_id: str, error: str) -> JobRecord:
        record = self.load(job_id)
        return self._save(
            replace(record, status=JobStatus.FAILED, error=str(error), updated_at=_now())
        )


    def cancel(self, job_id: str) -> JobRecord:
        record = self.load(job_id)
        return self._save(
            replace(record, status=JobStatus.CANCELLED, error=None, updated_at=_now())
        )

    def complete(self, job_id: str) -> JobRecord:
        record = self.load(job_id)
        return self._save(
            replace(record, status=JobStatus.COMPLETED, progress=1.0, error=None, updated_at=_now())
        )

    def retry(self, job_id: str) -> JobRecord:
        record = self.load(job_id)
        if record.status is not JobStatus.FAILED:
            raise ValueError("only failed jobs can be retried")
        return self._save(
            replace(
                record,
                status=JobStatus.PENDING,
                attempts=record.attempts + 1,
                progress=0.0,
                error=None,
                updated_at=_now(),
            )
        )

    def list_recent(self, *, limit: int = 20) -> tuple[JobRecord, ...]:
        if limit < 1:
            return ()
        if not self.root.is_dir():
            return ()
        records: list[JobRecord] = []
        for path in self.root.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    records.append(JobRecord.from_dict(payload))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        records.sort(key=lambda item: item.updated_at, reverse=True)
        return tuple(records[:limit])

    def _save(self, record: JobRecord) -> JobRecord:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path(record.id)
        temp = self.root / f".{record.id}.json.tmp"
        temp.write_text(json.dumps(record.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
        return record

    @staticmethod
    def _validate_id(job_id: str) -> None:
        if not _JOB_ID.fullmatch(job_id):
            raise ValueError(f"invalid job id: {job_id!r}")
