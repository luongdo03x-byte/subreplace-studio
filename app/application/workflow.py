from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from app.core.jobs.store import JobStore
from app.core.project.service import ProjectService
from app.models.project import Project
from app.workers.pipeline_worker import PipelineStage, PipelineWorker, project_checkpoint_callback
from app.workers.process_worker import ProcessStageWorker
from app.workers.protocol import WorkerCommand


@dataclass(frozen=True, slots=True)
class WorkflowHandle:
    job_id: str
    job_store: JobStore
    worker: PipelineWorker
    process_worker: object

    def cancel(self) -> None:
        self.worker.cancel()
        cancel = getattr(self.process_worker, "cancel", None)
        if callable(cancel):
            cancel()


class WorkflowController:
    def __init__(
        self,
        *,
        process_worker: ProcessStageWorker | None = None,
        project_service: ProjectService | None = None,
    ) -> None:
        self.process_worker = process_worker or ProcessStageWorker()
        self.project_service = project_service or ProjectService()

    @staticmethod
    def _job_store(project: Project) -> JobStore:
        return JobStore(project.root / "jobs")

    def _pipeline(
        self,
        project: Project,
        job_id: str,
        commands: Sequence[WorkerCommand],
        *,
        completed_stages: set[str] | None = None,
        on_progress: Callable | None = None,
    ) -> WorkflowHandle:
        job_store = self._job_store(project)
        stages: list[PipelineStage] = []
        for template in commands:
            command = WorkerCommand(job_id, template.stage, str(project.root), dict(template.config))
            stages.append(
                PipelineStage(
                    name=template.stage,
                    run=lambda command=command: self.process_worker.run(command),
                )
            )
        worker = PipelineWorker(
            stages,
            on_progress=on_progress,
            on_stage_complete=project_checkpoint_callback(self.project_service, project),
            job_store=job_store,
            job_id=job_id,
            completed_stages=set(completed_stages or ()),
        )
        worker.start()
        return WorkflowHandle(job_id, job_store, worker, self.process_worker)

    def start(
        self,
        project: Project,
        commands: Sequence[WorkerCommand],
        *,
        on_progress: Callable | None = None,
    ) -> WorkflowHandle:
        if not commands:
            raise ValueError("workflow requires at least one stage")
        store = self._job_store(project)
        record = store.create(stage=commands[0].stage, metadata={"project_id": project.id})
        return self._pipeline(project, record.id, commands, on_progress=on_progress)

    def retry(
        self,
        project: Project,
        job_id: str,
        commands: Sequence[WorkerCommand],
        *,
        on_progress: Callable | None = None,
    ) -> WorkflowHandle:
        store = self._job_store(project)
        record = store.retry(job_id)
        completed = set(record.completed_stages)
        return self._pipeline(
            project,
            job_id,
            commands,
            completed_stages=completed,
            on_progress=on_progress,
        )
