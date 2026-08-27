from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.application.default_workflow import build_full_commands
from app.application.workflow import WorkflowController
from app.core.project.service import ProjectService
from app.models.project import Project


class StudioSession:
    def __init__(
        self,
        *,
        workflow: WorkflowController | None = None,
        project_service: ProjectService | None = None,
    ) -> None:
        self.workflow = workflow or WorkflowController()
        self.project_service = project_service or ProjectService()
        self.current_project: Project | None = None
        self.current_handle = None

    def create_project(
        self,
        *,
        source_path: str | Path,
        project_root: str | Path,
        name: str,
        target_language: str,
    ) -> Project:
        project = self.project_service.create(
            project_root,
            source_path=source_path,
            name=name,
            target_language=target_language,
        )
        self.current_project = project
        return project

    def open_project(self, root: str | Path) -> Project:
        project = self.project_service.open(root)
        self.current_project = project
        return project

    def start_full(
        self,
        project: Project,
        *,
        translation_config: dict[str, object],
        temporal_config: dict[str, object] | None = None,
        on_progress: Callable | None = None,
        has_audio: bool = True,
    ):
        commands = build_full_commands(
            project,
            translation_config=translation_config,
            temporal_config=temporal_config,
            has_audio=has_audio,
        )
        handle = self.workflow.start(project, commands, on_progress=on_progress)
        self.current_project = project
        self.current_handle = handle
        return handle

    def retry_full(
        self,
        project: Project,
        job_id: str,
        *,
        translation_config: dict[str, object],
        temporal_config: dict[str, object] | None = None,
        on_progress: Callable | None = None,
        has_audio: bool = True,
    ):
        commands = build_full_commands(
            project,
            translation_config=translation_config,
            temporal_config=temporal_config,
            has_audio=has_audio,
        )
        handle = self.workflow.retry(project, job_id, commands, on_progress=on_progress)
        self.current_project = project
        self.current_handle = handle
        return handle

    def cancel(self) -> None:
        handle = self.current_handle
        if handle is not None:
            cancel = getattr(handle, "cancel", None)
            if callable(cancel):
                cancel()
