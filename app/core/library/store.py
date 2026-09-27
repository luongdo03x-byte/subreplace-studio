from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Iterator
from uuid import uuid4

from app.core.settings import app_data_root

from .models import Episode, EpisodeStatus, PublicationJob, PublicationStatus, Series


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LibraryStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else app_data_root() / "library.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL);
                INSERT INTO schema_version(version) SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM schema_version);
                CREATE TABLE IF NOT EXISTS series(
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, source_folder TEXT NOT NULL,
                    base_title TEXT NOT NULL, target_language TEXT NOT NULL CHECK(target_language IN ('vi','en')),
                    output_folder TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS episodes(
                    id TEXT PRIMARY KEY, series_id TEXT NOT NULL REFERENCES series(id) ON DELETE CASCADE,
                    number INTEGER NOT NULL CHECK(number > 0), source_filename TEXT NOT NULL,
                    source_path TEXT NOT NULL, final_video_path TEXT,
                    processing_status TEXT NOT NULL, qa_status TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(series_id, number)
                );
                CREATE TABLE IF NOT EXISTS assets(
                    id TEXT PRIMARY KEY, episode_id TEXT NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL, path TEXT NOT NULL, size_bytes INTEGER NOT NULL,
                    created_at TEXT NOT NULL, UNIQUE(episode_id, kind, path)
                );
                CREATE TABLE IF NOT EXISTS publication_jobs(
                    id TEXT PRIMARY KEY, episode_id TEXT NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
                    platform TEXT NOT NULL, account_id TEXT NOT NULL, publication_type TEXT NOT NULL,
                    scheduled_at TEXT, timezone TEXT NOT NULL, schedule_source TEXT NOT NULL,
                    status TEXT NOT NULL, remote_id TEXT, retry_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT, metadata_snapshot TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(episode_id, platform, account_id, publication_type)
                );
                CREATE TABLE IF NOT EXISTS audit_events(
                    id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
                    event_type TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
            """)

    @staticmethod
    def _series(row: sqlite3.Row) -> Series:
        return Series(row["id"], row["name"], Path(row["source_folder"]), row["base_title"],
                      row["target_language"], Path(row["output_folder"]), row["created_at"], row["updated_at"])

    @staticmethod
    def _episode(row: sqlite3.Row) -> Episode:
        final = Path(row["final_video_path"]) if row["final_video_path"] else None
        return Episode(row["id"], row["series_id"], row["number"], row["source_filename"],
                       Path(row["source_path"]), final, EpisodeStatus(row["processing_status"]),
                       row["qa_status"], row["created_at"], row["updated_at"])

    @staticmethod
    def _job(row: sqlite3.Row) -> PublicationJob:
        return PublicationJob(
            row["id"], row["episode_id"], row["platform"], row["account_id"], row["publication_type"],
            row["scheduled_at"], row["timezone"], row["schedule_source"], PublicationStatus(row["status"]),
            row["remote_id"], row["retry_count"], row["last_error"], json.loads(row["metadata_snapshot"]),
            row["created_at"], row["updated_at"],
        )

    def create_series(self, *, name: str, source_folder: Path, base_title: str,
                      target_language: str, output_folder: Path) -> Series:
        if target_language not in {"vi", "en"}:
            raise ValueError("target_language must be vi or en")
        if not name.strip() or not base_title.strip():
            raise ValueError("series name and base title are required")
        series_id, now = str(uuid4()), _now()
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO series VALUES(?,?,?,?,?,?,?,?)",
                (series_id, name.strip(), str(source_folder.resolve()), base_title.strip(), target_language,
                 str(output_folder.resolve()), now, now),
            )
            self._audit(connection, "series", series_id, "SERIES_CREATED", {"name": name.strip()})
        return self.get_series(series_id)

    def get_series(self, series_id: str) -> Series:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM series WHERE id=?", (series_id,)).fetchone()
        if row is None:
            raise KeyError(series_id)
        return self._series(row)

    def list_series(self) -> tuple[Series, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM series ORDER BY created_at, name").fetchall()
        return tuple(self._series(row) for row in rows)

    def find_series(self, source_folder: Path, target_language: str) -> Series | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT * FROM series WHERE source_folder=? AND target_language=?
                   ORDER BY (SELECT COUNT(*) FROM episodes WHERE episodes.series_id=series.id) DESC,
                            created_at LIMIT 1""",
                (str(source_folder.expanduser().resolve()), target_language),
            ).fetchone()
        return self._series(row) if row is not None else None

    def delete_series(self, series_id: str) -> None:
        with self._transaction() as connection:
            series = connection.execute("SELECT name FROM series WHERE id=?", (series_id,)).fetchone()
            if series is None:
                raise KeyError(series_id)
            self._audit(connection, "series", series_id, "SERIES_DELETED", {"name": series["name"]})
            connection.execute("DELETE FROM series WHERE id=?", (series_id,))

    def add_episode(self, series_id: str, number: int, source_path: Path) -> Episode:
        episode_id, now = str(uuid4()), _now()
        source = source_path.resolve()
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO episodes VALUES(?,?,?,?,?,?,?,?,?,?)",
                (episode_id, series_id, number, source.name, str(source), None,
                 EpisodeStatus.WAITING.value, "pending", now, now),
            )
            self._audit(connection, "episode", episode_id, "EPISODE_IMPORTED", {"number": number})
        return self.get_episode(episode_id)

    def get_episode(self, episode_id: str) -> Episode:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM episodes WHERE id=?", (episode_id,)).fetchone()
        if row is None:
            raise KeyError(episode_id)
        return self._episode(row)

    def list_episodes(self, series_id: str) -> tuple[Episode, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM episodes WHERE series_id=? ORDER BY number", (series_id,)).fetchall()
        return tuple(self._episode(row) for row in rows)

    def register_final_video(self, episode_id: str, path: Path) -> Episode:
        final = path.expanduser().resolve()
        if not final.is_file() or final.stat().st_size == 0:
            raise FileNotFoundError(final)
        now = _now()
        with self._transaction() as connection:
            connection.execute(
                "UPDATE episodes SET final_video_path=?,processing_status=?,qa_status=?,updated_at=? WHERE id=?",
                (str(final), EpisodeStatus.COMPLETED.value, "pass", now, episode_id),
            )
            if connection.total_changes == 0:
                raise KeyError(episode_id)
            connection.execute(
                "INSERT OR IGNORE INTO assets VALUES(?,?,?,?,?,?)",
                (str(uuid4()), episode_id, "final_video", str(final), final.stat().st_size, now),
            )
            self._audit(connection, "episode", episode_id, "FINAL_VIDEO_REGISTERED", {"path": str(final)})
        return self.get_episode(episode_id)

    def create_youtube_job(self, episode_id: str, *, account_id: str, scheduled_at: str | None,
                           timezone_name: str, metadata: dict) -> PublicationJob:
        job_id, now = str(uuid4()), _now()
        status = PublicationStatus.SCHEDULED if scheduled_at else PublicationStatus.DRAFT
        with self._transaction() as connection:
            inserted = connection.execute(
                """INSERT INTO publication_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(episode_id,platform,account_id,publication_type) DO NOTHING""",
                (job_id, episode_id, "youtube", account_id, "youtube_short", scheduled_at, timezone_name,
                 "manual_override" if scheduled_at else "manual", status.value, None, 0, None,
                 json.dumps(metadata, ensure_ascii=False), now, now),
            )
            row = connection.execute(
                "SELECT * FROM publication_jobs WHERE episode_id=? AND platform='youtube' AND account_id=? AND publication_type='youtube_short'",
                (episode_id, account_id),
            ).fetchone()
            assert row is not None
            if inserted.rowcount:
                self._audit(connection, "publication_job", row["id"], "PUBLICATION_CREATED", {})
        return self._job(row)

    def get_job(self, job_id: str) -> PublicationJob:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM publication_jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return self._job(row)

    def list_jobs(self) -> tuple[PublicationJob, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM publication_jobs ORDER BY created_at").fetchall()
        return tuple(self._job(row) for row in rows)

    def update_job(self, job_id: str, status: PublicationStatus, *, remote_id: str | None = None,
                   error: str | None = None, increment_retry: bool = False) -> PublicationJob:
        now = _now()
        with self._transaction() as connection:
            connection.execute(
                """UPDATE publication_jobs SET status=?,remote_id=COALESCE(?,remote_id),last_error=?,
                   retry_count=retry_count+?,updated_at=? WHERE id=?""",
                (status.value, remote_id, error, int(increment_retry), now, job_id),
            )
            if connection.total_changes == 0:
                raise KeyError(job_id)
            self._audit(connection, "publication_job", job_id, "PUBLICATION_STATUS_CHANGED", {"status": status.value})
        return self.get_job(job_id)

    @staticmethod
    def _audit(connection: sqlite3.Connection, entity_type: str, entity_id: str,
               event_type: str, payload: dict) -> None:
        connection.execute(
            "INSERT INTO audit_events VALUES(?,?,?,?,?,?)",
            (str(uuid4()), entity_type, entity_id, event_type, json.dumps(payload, ensure_ascii=False), _now()),
        )
