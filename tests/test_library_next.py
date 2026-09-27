from __future__ import annotations

from pathlib import Path

import pytest

from app.application.library_service import LibraryService
from app.core.library import LibraryStore, analyze_episode_files, parse_episode_number


def test_episode_parser_prioritizes_labeled_number():
    assert parse_episode_number("drama_2026_ep_15_1080p.mp4") == 15
    assert parse_episode_number("episode-2.mp4") == 2
    assert parse_episode_number("tập_8.mp4") == 8
    assert parse_episode_number("10.mp4") == 10
    assert parse_episode_number("01_1_vi.mp4") == 1


def test_import_analysis_reports_missing_and_duplicate(tmp_path):
    paths = [tmp_path / name for name in ("ep_1.mp4", "ep_2.mp4", "ep_2_final.mp4", "ep_4.mp4")]
    for path in paths:
        path.write_bytes(b"video")
    analysis = analyze_episode_files(paths)
    assert analysis.missing == (3,)
    assert tuple(analysis.duplicates) == (2,)
    assert not analysis.valid


def test_library_persists_series_episode_asset_and_idempotent_job(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    output.mkdir()
    for number in (1, 2, 10):
        (source / f"ep_{number}.mp4").write_bytes(b"source")

    store = LibraryStore(tmp_path / "next.sqlite3")
    service = LibraryService(store)
    series = service.create_series_from_folder(
        name="Drama", folder=source, base_title="A new life", target_language="vi", output_folder=output,
    )
    episodes = service.list_episodes(series.id)
    assert [episode.number for episode in episodes] == [1, 2, 10]

    final = output / "ep_1_vi.mp4"
    final.write_bytes(b"translated")
    episode = service.register_final_video(episodes[0].id, final)
    assert episode.final_video_path == final.resolve()
    assert episode.qa_status == "pass"

    metadata = {"title": "A new life tập 1", "privacy_status": "private"}
    first = service.create_youtube_job(
        episode.id, account_id="channel-1", scheduled_at=None,
        timezone_name="Asia/Ho_Chi_Minh", metadata=metadata,
    )
    second = service.create_youtube_job(
        episode.id, account_id="channel-1", scheduled_at=None,
        timezone_name="Asia/Ho_Chi_Minh", metadata=metadata,
    )
    assert first.id == second.id
    assert len(store.list_jobs()) == 1

    with pytest.raises(ValueError, match="đã tồn tại"):
        service.create_series_from_folder(
            name="Duplicate", folder=source, base_title="Duplicate", target_language="vi", output_folder=output,
        )
    assert len(service.list_series()) == 1
    service.delete_series(series.id)
    assert service.list_series() == ()
    assert final.is_file()


def test_import_completed_videos_registers_each_source_as_final(tmp_path):
    source = tmp_path / "finals"; output = tmp_path / "output"
    source.mkdir(); output.mkdir()
    for number in (1, 2): (source / f"{number:02d}_{number}_vi.mp4").write_bytes(b"final")
    service = LibraryService(LibraryStore(tmp_path / "library.sqlite3"))
    series = service.create_series_from_folder(
        name="Ready", folder=source, base_title="Ready", target_language="vi",
        output_folder=output, import_as_final=True,
    )
    episodes = service.list_episodes(series.id)
    assert [episode.processing_status.value for episode in episodes] == ["completed", "completed"]
    assert [episode.qa_status for episode in episodes] == ["pass", "pass"]
    assert [episode.final_video_path for episode in episodes] == [episode.source_path for episode in episodes]
