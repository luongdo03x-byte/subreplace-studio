from __future__ import annotations

import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from app.core.jobs.models import JobStatus
from app.core.media.ffmpeg import FFmpegMedia

from .view_model import ProjectStartRequest, StudioViewModel


@dataclass(frozen=True, slots=True)
class BatchItem:
    request: ProjectStartRequest
    output_path: Path


@dataclass(frozen=True, slots=True)
class BatchItemResult:
    source_path: Path
    output_path: Path | None
    project_root: Path | None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class BatchResult:
    items: tuple[BatchItemResult, ...]
    merged_output: Path | None = None
    merge_error: str | None = None
    cancelled: bool = False
    total: int = 0

    @property
    def successful(self) -> tuple[BatchItemResult, ...]:
        return tuple(item for item in self.items if item.output_path is not None)


class BatchController:
    def __init__(self, view_model: StudioViewModel, *, media: FFmpegMedia | None = None) -> None:
        self.view_model = view_model
        self.media = media or FFmpegMedia()
        self._cancelled = threading.Event()
        self._lock = threading.Lock()
        self._active_handle = None

    def cancel(self) -> None:
        self._cancelled.set()
        with self._lock:
            handle = self._active_handle
        if handle is not None:
            handle.cancel()

    @staticmethod
    def _notify(callback: Callable | None, *args) -> None:
        if callback is None:
            return
        try:
            callback(*args)
        except Exception:
            # UI reporting must never terminate the worker queue.
            return

    @staticmethod
    def _publish(source: Path, destination: Path) -> Path:
        if not source.is_file() or source.stat().st_size == 0:
            raise FileNotFoundError(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.tmp")
        try:
            shutil.copy2(source, temporary)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        destination.with_suffix(".srt").unlink(missing_ok=True)
        return destination

    def run(
        self,
        items: Sequence[BatchItem],
        *,
        merged_output: Path | None = None,
        on_progress: Callable[[int, int, object], None] | None = None,
        on_item: Callable[[int, int, Path, str, str], None] | None = None,
    ) -> BatchResult:
        if not items:
            raise ValueError("batch requires at least one video")
        results: list[BatchItemResult] = []
        total = len(items)
        for index, item in enumerate(items, start=1):
            source = Path(item.request.source_path)
            if self._cancelled.is_set():
                break
            self._notify(on_item, index, total, source, "started", "")
            project = None
            try:
                handle, _report = self.view_model.start(
                    item.request,
                    on_progress=lambda event, i=index: self._notify(on_progress, i, total, event),
                )
                project = self.view_model.session.current_project
                with self._lock:
                    self._active_handle = handle
                    cancelled = self._cancelled.is_set()
                if cancelled:
                    handle.cancel()
                handle.worker.join()
                record = handle.job_store.load(handle.job_id)
                if self._cancelled.is_set() or record.status == JobStatus.CANCELLED:
                    break
                if record.status != JobStatus.COMPLETED or project is None:
                    raise RuntimeError(record.error or f"job ended with status {record.status.value}")
                final = project.root / "exports" / f"final_{project.target_language}.mp4"
                published = self._publish(final, item.output_path)
                result = BatchItemResult(source.resolve(), published, project.root)
                results.append(result)
                self._notify(on_item, index, total, source, "completed", str(published))
            except Exception as exc:
                results.append(BatchItemResult(source.resolve(), None, project.root if project else None, str(exc)))
                self._notify(on_item, index, total, source, "failed", str(exc))
            finally:
                with self._lock:
                    self._active_handle = None

        merged = None
        merge_error = None
        successful = [item.output_path for item in results if item.output_path is not None]
        if merged_output is not None and not self._cancelled.is_set() and len(successful) >= 2:
            try:
                merged = self.media.concat(successful, merged_output, cancel_event=self._cancelled)
            except Exception as exc:
                merge_error = str(exc)
        return BatchResult(tuple(results), merged, merge_error, self._cancelled.is_set(), total)
