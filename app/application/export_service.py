from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from app.core.project.package import ProjectPackageMode, export_project_package
from app.models.project import Project


@dataclass(frozen=True, slots=True)
class ExportResult:
    output_dir: Path
    files: tuple[Path, ...]


class ExportService:
    def export(
        self,
        project: Project,
        output_dir: str | Path,
        *,
        include_subtitle: bool = False,
        include_clean: bool = False,
        include_project: bool = False,
    ) -> ExportResult:
        destination = Path(output_dir).resolve()
        destination.mkdir(parents=True, exist_ok=True)
        final = project.root / "exports" / f"final_{project.target_language}.mp4"
        if not final.is_file():
            raise FileNotFoundError(final)
        exported: list[Path] = []
        final_target = destination / f"{project.name}-{project.target_language}.mp4"
        shutil.copy2(final, final_target)
        exported.append(final_target)

        subtitle = project.root / "subtitles" / f"target_{project.target_language}.srt"
        if include_subtitle and subtitle.is_file():
            subtitle_target = destination / f"{project.name}-{project.target_language}.srt"
            shutil.copy2(subtitle, subtitle_target)
            exported.append(subtitle_target)

        if include_clean:
            clean = project.root / "cache" / "clean" / "clean.mkv"
            if clean.is_file():
                clean_target = destination / f"{project.name}-clean.mkv"
                shutil.copy2(clean, clean_target)
                exported.append(clean_target)

        if include_project:
            package = export_project_package(
                project, destination / f"{project.name}.subreplace", ProjectPackageMode.PORTABLE
            )
            exported.append(package)
        return ExportResult(destination, tuple(exported))
