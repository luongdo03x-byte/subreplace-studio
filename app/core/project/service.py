from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any, Mapping

from app.models.enums import ProjectState
from app.models.project import Project

from .migrations import CURRENT_PROJECT_SCHEMA_VERSION, migrate_payload


CACHE_DIRS = ("audio", "frames", "detection", "ocr", "asr", "masks", "clean", "translation")


class ProjectService:
    def create(
        self,
        root: str | Path,
        *,
        source_path: str | Path,
        name: str,
        target_language: str,
    ) -> Project:
        if target_language not in {"vi", "en"}:
            raise ValueError("target language must be one of: vi, en")
        source = Path(source_path)
        if not source.is_file():
            raise FileNotFoundError(source)
        project_root = Path(root)
        if project_root.exists() and any(project_root.iterdir()):
            raise FileExistsError(f"project directory is not empty: {project_root}")
        (project_root / "source").mkdir(parents=True, exist_ok=True)
        for name_ in CACHE_DIRS:
            (project_root / "cache" / name_).mkdir(parents=True, exist_ok=True)
        (project_root / "subtitles").mkdir(parents=True, exist_ok=True)
        (project_root / "exports").mkdir(parents=True, exist_ok=True)
        (project_root / "jobs").mkdir(parents=True, exist_ok=True)
        stored_source = project_root / "source" / "source.mp4"
        shutil.copy2(source, stored_source)
        project = Project(
            id=uuid.uuid4().hex,
            name=name,
            root=project_root.resolve(),
            source_path=stored_source.resolve(),
            target_language=target_language,
        )
        self.save(project)
        return project

    def save(self, project: Project) -> None:
        payload = self._to_payload(project)
        self._write_payload(project.root / "project.json", payload)

    def open(self, root: str | Path) -> Project:
        project_root = Path(root).resolve()
        path = project_root / "project.json"
        if not path.is_file():
            raise FileNotFoundError(path)
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw_payload, dict):
            raise ValueError("project.json must contain an object")
        old_version = raw_payload.get("schema_version", 1)
        payload = migrate_payload(raw_payload)
        if old_version != payload["schema_version"]:
            backup = project_root / f"project.v{old_version}.backup.json"
            if not backup.exists():
                self._write_payload(backup, raw_payload)
            self._write_payload(path, payload)
        source_path = (project_root / str(payload["source_path"])).resolve()
        if project_root != source_path and project_root not in source_path.parents:
            raise ValueError("project source_path escapes project root")
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        return Project(
            id=str(payload["id"]),
            name=str(payload["name"]),
            root=project_root,
            source_path=source_path,
            target_language=str(payload["target_language"]),
            state=ProjectState(str(payload["state"])),
            glossary=dict(payload.get("glossary", {})),
            completed_stages=set(payload.get("completed_stages", [])),
            subtitle_edits=dict(payload.get("subtitle_edits", {})),
            approvals=set(payload.get("approvals", [])),
            settings=dict(payload.get("settings", {})),
        )

    def mark_stage_complete(self, project: Project, stage: str) -> None:
        project.completed_stages.add(stage)
        self.save(project)

    @staticmethod
    def _write_payload(path: Path, payload: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f".{path.name}.tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    @staticmethod
    def _to_payload(project: Project) -> dict[str, Any]:
        project.root.mkdir(parents=True, exist_ok=True)
        relative_source = project.source_path.resolve().relative_to(project.root.resolve())
        return {
            "schema_version": CURRENT_PROJECT_SCHEMA_VERSION,
            "id": project.id,
            "name": project.name,
            "source_path": relative_source.as_posix(),
            "target_language": project.target_language,
            "state": project.state.value,
            "glossary": dict(sorted(project.glossary.items())),
            "completed_stages": sorted(project.completed_stages),
            "subtitle_edits": project.subtitle_edits,
            "approvals": sorted(project.approvals),
            "settings": project.settings,
        }
