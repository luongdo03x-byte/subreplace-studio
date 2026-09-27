from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class EpisodeStatus(str, Enum):
    WAITING = "waiting"
    PROCESSING = "processing"
    READY_FOR_REVIEW = "ready_for_review"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


class PublicationStatus(str, Enum):
    DRAFT = "draft"
    BLOCKED_BY_SEQUENCE = "blocked_by_sequence"
    SCHEDULED = "scheduled"
    VALIDATING = "validating"
    UPLOADING = "uploading"
    REMOTE_PROCESSING = "remote_processing"
    PUBLISHED = "published"
    RETRY_WAIT = "retry_wait"
    FAILED = "failed"
    FAILED_AUTH = "failed_auth"
    CANCELLED = "cancelled"
    UNKNOWN_REMOTE_RESULT = "unknown_remote_result"


@dataclass(frozen=True, slots=True)
class Series:
    id: str
    name: str
    source_folder: Path
    base_title: str
    target_language: str
    output_folder: Path
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class Episode:
    id: str
    series_id: str
    number: int
    source_filename: str
    source_path: Path
    final_video_path: Path | None
    processing_status: EpisodeStatus
    qa_status: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class PublicationJob:
    id: str
    episode_id: str
    platform: str
    account_id: str
    publication_type: str
    scheduled_at: str | None
    timezone: str
    schedule_source: str
    status: PublicationStatus
    remote_id: str | None
    retry_count: int
    last_error: str | None
    metadata_snapshot: dict
    created_at: str
    updated_at: str
