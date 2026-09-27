from __future__ import annotations

from pathlib import Path

from app.core.library.models import Episode, PublicationJob, Series
from app.core.library.parser import ImportAnalysis, analyze_episode_files
from app.core.library.store import LibraryStore


class LibraryService:
    VIDEO_SUFFIXES = frozenset({".mp4", ".mkv", ".mov", ".avi"})

    def __init__(self, store: LibraryStore | None = None) -> None:
        self.store = store or LibraryStore()

    def analyze_folder(self, folder: str | Path) -> ImportAnalysis:
        root = Path(folder).expanduser().resolve()
        if not root.is_dir():
            raise NotADirectoryError(root)
        paths = [path for path in root.iterdir() if path.is_file() and path.suffix.casefold() in self.VIDEO_SUFFIXES]
        return analyze_episode_files(paths)

    def create_series_from_folder(self, *, name: str, folder: str | Path, base_title: str,
                                  target_language: str, output_folder: str | Path,
                                  import_as_final: bool = False) -> Series:
        root = Path(folder).expanduser().resolve()
        analysis = self.analyze_folder(root)
        if not analysis.valid:
            duplicate_text = ", ".join(str(number) for number in sorted(analysis.duplicates))
            details = list(analysis.errors)
            if duplicate_text:
                details.append(f"Duplicate episodes: {duplicate_text}")
            raise ValueError("; ".join(details))
        existing = self.store.find_series(root, target_language)
        if existing is not None:
            raise ValueError(f"Series đã tồn tại cho thư mục này: {existing.name}")
        series = self.store.create_series(
            name=name, source_folder=root, base_title=base_title,
            target_language=target_language, output_folder=Path(output_folder).expanduser(),
        )
        for number, path in analysis.episodes:
            episode = self.store.add_episode(series.id, number, path)
            if import_as_final:
                self.store.register_final_video(episode.id, path)
        return series

    def list_series(self) -> tuple[Series, ...]:
        return self.store.list_series()

    def list_episodes(self, series_id: str) -> tuple[Episode, ...]:
        return self.store.list_episodes(series_id)

    def delete_series(self, series_id: str) -> None:
        self.store.delete_series(series_id)

    def register_final_video(self, episode_id: str, path: str | Path) -> Episode:
        return self.store.register_final_video(episode_id, Path(path))

    def create_youtube_job(self, episode_id: str, *, account_id: str, scheduled_at: str | None,
                           timezone_name: str, metadata: dict) -> PublicationJob:
        episode = self.store.get_episode(episode_id)
        if episode.final_video_path is None or episode.qa_status != "pass":
            raise ValueError("Episode requires a registered final video with QA pass")
        return self.store.create_youtube_job(
            episode_id, account_id=account_id, scheduled_at=scheduled_at,
            timezone_name=timezone_name, metadata=metadata,
        )
