from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.application.library_service import LibraryService
from app.application.youtube_publishing import YouTubePublishingService
from app.core.library import LibraryStore, PublicationStatus
from app.providers.youtube import YouTubeVideoMetadata
from app.providers.youtube.publisher import YouTubePublisher


class _FakePublisher:
    def __init__(self):
        self.paths = []

    def upload(self, path, metadata, *, progress=None, on_remote_id=None):
        self.paths.append(path)
        if on_remote_id:
            on_remote_id("youtube-video-1")
        if progress:
            progress(1.0)
        return "youtube-video-1"

    def processing_status(self, _video_id):
        return "succeeded", None


def _job(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir(); output.mkdir()
    (source / "ep_1.mp4").write_bytes(b"source")
    store = LibraryStore(tmp_path / "library.sqlite3")
    library = LibraryService(store)
    series = library.create_series_from_folder(
        name="Drama", folder=source, base_title="Story", target_language="vi", output_folder=output,
    )
    episode = library.list_episodes(series.id)[0]
    final = output / "ep_1_vi.mp4"
    final.write_bytes(b"final")
    library.register_final_video(episode.id, final)
    job = library.create_youtube_job(
        episode.id, account_id="channel", scheduled_at=None,
        timezone_name="Asia/Ho_Chi_Minh", metadata={"title": "Story tập 1"},
    )
    return store, job


def test_scheduled_metadata_forces_private_and_utc():
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    body = YouTubeVideoMetadata("Title", privacy_status="public", publish_at=future).body()
    assert body["status"]["privacyStatus"] == "private"
    assert body["status"]["publishAt"].endswith("Z")


def test_publish_saves_remote_id_before_polling(tmp_path):
    store, job = _job(tmp_path)
    publisher = _FakePublisher()
    service = YouTubePublishingService(store, publisher=publisher)
    assert service.publish(job.id) == "youtube-video-1"
    uploaded = store.get_job(job.id)
    assert uploaded.remote_id == "youtube-video-1"
    assert uploaded.status == PublicationStatus.REMOTE_PROCESSING
    assert service.refresh_remote_status(job.id) == PublicationStatus.PUBLISHED


def test_resumable_uploader_reports_progress_without_duplicate(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")

    class Request:
        def next_chunk(self, num_retries=0):
            return SimpleNamespace(progress=lambda: 0.5), {"id": "remote-1"}

    service = SimpleNamespace(videos=lambda: SimpleNamespace(insert=lambda **_kwargs: Request()))
    publisher = YouTubePublisher(service_factory=lambda _credentials: service)
    publisher._credentials = lambda: object()
    publisher._libraries = lambda: (object, object, object, object, object, lambda *args, **kwargs: object())
    progress = []
    assert publisher.upload(video, YouTubeVideoMetadata("Title"), progress=progress.append) == "remote-1"
    assert progress == [0.5, 1.0]
    assert publisher.upload(video, YouTubeVideoMetadata("Title"), remote_id="known") == "known"
