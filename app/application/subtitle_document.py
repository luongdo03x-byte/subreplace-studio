from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from app.core.project.service import ProjectService
from app.models.project import Project


@dataclass(frozen=True, slots=True)
class SubtitleEditorRow:
    id: str
    source_text: str
    target_text: str
    review_status: str
    text_type: str
    ocr_confidence: float
    classification_confidence: float


class SubtitleDocumentService:
    def __init__(self, *, project_service: ProjectService | None = None) -> None:
        self.project_service = project_service or ProjectService()

    @staticmethod
    def _classified_path(project: Project) -> Path:
        return project.root / "cache" / "detection" / "classified.json"

    @staticmethod
    def _translated_path(project: Project) -> Path:
        return project.root / "cache" / "translation" / f"translated_{project.target_language}.json"

    @staticmethod
    def _read_array(path: Path) -> list[dict]:
        if not path.is_file():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"expected JSON array: {path}")
        return [dict(item) for item in payload if isinstance(item, dict)]

    @staticmethod
    def _write_array(path: Path, payload: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f".{path.name}.tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    def load(self, project: Project) -> tuple[SubtitleEditorRow, ...]:
        classified = self._read_array(self._classified_path(project))
        translated = {
            str(item.get("id") or ""): item
            for item in self._read_array(self._translated_path(project))
        }
        rows = []
        for item in classified:
            identifier = str(item.get("event_id") or "")
            target = translated.get(identifier, {})
            rows.append(
                SubtitleEditorRow(
                    id=identifier,
                    source_text=str(item.get("text") or ""),
                    target_text=str(target.get("target_text") or target.get("optimized_translation") or ""),
                    review_status=str(item.get("review_status") or "needs_review"),
                    text_type=str(item.get("text_type") or "unknown"),
                    ocr_confidence=float(item.get("confidence", 0.0)),
                    classification_confidence=float(item.get("classification_confidence", 0.0)),
                )
            )
        return tuple(rows)


    def update_source_text(self, project: Project, segment_id: str, text: str) -> None:
        classified_path = self._classified_path(project)
        payload = self._read_array(classified_path)
        changed = False
        value = text.strip()
        for item in payload:
            if str(item.get("event_id") or "") == segment_id:
                item["text"] = value
                changed = True
                break
        if not changed:
            raise KeyError(segment_id)
        self._write_array(classified_path, payload)
        project.subtitle_edits[f"source:{segment_id}"] = value
        self._invalidate(project, {"translate_events", "render_final"}, remove_translation=True)

    def set_review_decision(self, project: Project, segment_id: str, *, text_type: str) -> None:
        allowed = {"dialogue_subtitle", "watermark", "logo", "title", "scene_text", "ui_text", "decoration"}
        if text_type not in allowed:
            raise ValueError(f"unsupported review text_type: {text_type}")
        classified_path = self._classified_path(project)
        payload = self._read_array(classified_path)
        changed = False
        for item in payload:
            if str(item.get("event_id") or "") == segment_id:
                item["text_type"] = text_type
                item["review_status"] = "approved"
                changed = True
                break
        if not changed:
            raise KeyError(segment_id)
        self._write_array(classified_path, payload)
        project.approvals.add(segment_id)
        self._invalidate(
            project, {"erase_video", "translate_events", "render_final"},
            remove_clean=True, remove_translation=True,
        )

    def _invalidate(
        self, project: Project, stages: set[str], *, remove_clean: bool = False, remove_translation: bool = False
    ) -> None:
        project.completed_stages.difference_update(stages)
        if remove_clean:
            (project.root / "cache" / "clean" / "clean.mkv").unlink(missing_ok=True)
            (project.root / "cache" / "clean" / "erase-report.json").unlink(missing_ok=True)
        if remove_translation:
            self._translated_path(project).unlink(missing_ok=True)
            (project.root / "subtitles" / f"target_{project.target_language}.srt").unlink(missing_ok=True)
        (project.root / "exports" / f"final_{project.target_language}.mp4").unlink(missing_ok=True)
        self.project_service.save(project)

    def update_translation(self, project: Project, segment_id: str, text: str) -> None:
        translated_path = self._translated_path(project)
        payload = self._read_array(translated_path)
        changed = False
        for item in payload:
            if str(item.get("id") or "") != segment_id:
                continue
            value = text.strip()
            item["target_text"] = value
            item["natural_translation"] = value
            item["optimized_translation"] = value
            changed = True
            break
        if not changed:
            raise KeyError(segment_id)
        self._write_array(translated_path, payload)
        project.subtitle_edits[segment_id] = text.strip()
        project.completed_stages.discard("render_final")
        final = project.root / "exports" / f"final_{project.target_language}.mp4"
        final.unlink(missing_ok=True)
        self.project_service.save(project)
