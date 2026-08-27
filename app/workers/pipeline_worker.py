from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Sequence


class StageStatus(str, Enum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PipelineStage:
    name: str
    run: Callable[[], object]


@dataclass(frozen=True, slots=True)
class StageEvent:
    stage: str
    index: int
    total: int
    status: StageStatus
    progress: float
    message: str = ""


class PipelineWorker:
    def __init__(
        self,
        stages: Sequence[PipelineStage],
        *,
        on_progress: Callable[[StageEvent], None] | None = None,
        on_stage_complete: Callable[[str], None] | None = None,
        job_store=None,
        job_id: str | None = None,
        completed_stages: set[str] | None = None,
    ) -> None:
        self.stages = tuple(stages)
        self.on_progress = on_progress or (lambda _event: None)
        self.on_stage_complete = on_stage_complete or (lambda _stage: None)
        self.job_store = job_store
        self.job_id = job_id
        self.completed_stages = set(completed_stages or ())
        if self.job_store is not None and not self.job_id:
            raise ValueError("job_id is required when job_store is provided")
        self.results: dict[str, object] = {}
        self.error: BaseException | None = None
        self._thread: threading.Thread | None = None
        self._cancelled = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            raise RuntimeError("pipeline worker is already running")
        self._thread = threading.Thread(target=self._run, name="SubReplacePipelineWorker", daemon=True)
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    def cancel(self) -> None:
        self._cancelled.set()

    @property
    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _run(self) -> None:
        total = len(self.stages)
        for index, stage in enumerate(self.stages, start=1):
            if self._cancelled.is_set():
                if self.job_store is not None:
                    self.job_store.cancel(self.job_id)
                return
            if stage.name in self.completed_stages:
                self.results.setdefault(stage.name, None)
                self.on_progress(StageEvent(stage.name, index, total, StageStatus.COMPLETED, index / max(1, total), "resumed"))
                continue
            self.on_progress(StageEvent(stage.name, index, total, StageStatus.STARTED, (index - 1) / max(1, total)))
            if self.job_store is not None:
                self.job_store.begin_stage(self.job_id, stage.name)
                self.job_store.update_progress(self.job_id, (index - 1) / max(1, total))
            try:
                self.results[stage.name] = stage.run()
            except BaseException as exc:
                self.error = exc
                if self.job_store is not None:
                    self.job_store.fail(self.job_id, str(exc))
                self.on_progress(StageEvent(stage.name, index, total, StageStatus.FAILED, (index - 1) / max(1, total), str(exc)))
                return
            if self._cancelled.is_set():
                if self.job_store is not None:
                    self.job_store.cancel(self.job_id)
                return
            self.completed_stages.add(stage.name)
            if self.job_store is not None:
                self.job_store.complete_stage(self.job_id, stage.name)
                self.job_store.update_progress(self.job_id, index / max(1, total))
            self.on_stage_complete(stage.name)
            self.on_progress(StageEvent(stage.name, index, total, StageStatus.COMPLETED, index / max(1, total)))
        if self.job_store is not None:
            self.job_store.complete(self.job_id)


def project_checkpoint_callback(project_service, project):
    """Return a stage callback that atomically persists successful stage checkpoints."""
    def checkpoint(stage: str) -> None:
        project_service.mark_stage_complete(project, stage)
    return checkpoint


def process_pipeline_stage(name, worker, command, *, timeout: float | None = None) -> PipelineStage:
    """Wrap an isolated ProcessStageWorker command as an existing PipelineStage."""
    return PipelineStage(
        name=name,
        run=lambda: worker.run(command, timeout=timeout),
    )
