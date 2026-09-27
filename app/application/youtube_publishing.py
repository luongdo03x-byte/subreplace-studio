from __future__ import annotations

from app.core.library.models import PublicationStatus
from app.core.library.store import LibraryStore
from app.providers.youtube import YouTubeAuthError, YouTubePublisher, YouTubeVideoMetadata


class YouTubePublishingService:
    def __init__(self, store: LibraryStore, publisher: YouTubePublisher | None = None) -> None:
        self.store = store
        self.publisher = publisher or YouTubePublisher()

    def publish(self, job_id: str, *, progress=None) -> str:
        job = self.store.get_job(job_id)
        if job.platform != "youtube":
            raise ValueError("Job is not a YouTube publication")
        if job.remote_id:
            return job.remote_id
        episode = self.store.get_episode(job.episode_id)
        if episode.final_video_path is None:
            raise ValueError("Episode has no final video")
        metadata = YouTubeVideoMetadata(
            title=str(job.metadata_snapshot.get("title") or ""),
            description=str(job.metadata_snapshot.get("description") or ""),
            tags=tuple(str(value) for value in job.metadata_snapshot.get("tags", [])),
            category_id=str(job.metadata_snapshot.get("category_id") or "24"),
            privacy_status=str(job.metadata_snapshot.get("privacy_status") or "private"),
            publish_at=job.scheduled_at,
        )
        self.store.update_job(job.id, PublicationStatus.UPLOADING)
        try:
            video_id = self.publisher.upload(
                episode.final_video_path, metadata, progress=progress,
                on_remote_id=lambda value: self.store.update_job(
                    job.id, PublicationStatus.REMOTE_PROCESSING, remote_id=value,
                ),
            )
        except YouTubeAuthError as exc:
            self.store.update_job(job.id, PublicationStatus.FAILED_AUTH, error=str(exc))
            raise
        except Exception as exc:
            self.store.update_job(
                job.id, PublicationStatus.FAILED, error=str(exc), increment_retry=True,
            )
            raise
        if self.store.get_job(job.id).remote_id is None:
            self.store.update_job(job.id, PublicationStatus.REMOTE_PROCESSING, remote_id=video_id)
        return video_id

    def refresh_remote_status(self, job_id: str) -> PublicationStatus:
        job = self.store.get_job(job_id)
        if not job.remote_id:
            raise ValueError("Publication has no YouTube video ID")
        status, reason = self.publisher.processing_status(job.remote_id)
        if status == "succeeded":
            updated = PublicationStatus.PUBLISHED
        elif status in {"failed", "terminated", "rejected"}:
            updated = PublicationStatus.FAILED
        else:
            updated = PublicationStatus.REMOTE_PROCESSING
        self.store.update_job(job.id, updated, error=reason)
        return updated
