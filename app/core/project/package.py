from __future__ import annotations

from enum import Enum
import json
from pathlib import Path, PurePosixPath
import shutil
import zipfile

from app.models.project import Project

from .migrations import CURRENT_PROJECT_SCHEMA_VERSION
from .service import ProjectService

PACKAGE_FORMAT = "subreplace-project"
PACKAGE_VERSION = 1


class ProjectPackageMode(str, Enum):
    LIGHTWEIGHT = "lightweight"
    PORTABLE = "portable"
    ARCHIVE = "archive"


def export_project_package(
    project: Project,
    output_path: str | Path,
    mode: ProjectPackageMode = ProjectPackageMode.PORTABLE,
) -> Path:
    output = Path(output_path)
    if output.suffix.lower() != ".subreplace":
        output = output.with_suffix(".subreplace")
    output.parent.mkdir(parents=True, exist_ok=True)
    ProjectService().save(project)
    manifest = {
        "format": PACKAGE_FORMAT,
        "version": PACKAGE_VERSION,
        "mode": mode.value,
        "project_schema_version": CURRENT_PROJECT_SCHEMA_VERSION,
        "source_included": mode in {ProjectPackageMode.PORTABLE, ProjectPackageMode.ARCHIVE},
        "cache_included": mode is ProjectPackageMode.ARCHIVE,
    }
    temp = output.with_name(f".{output.name}.tmp")
    with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        _write_file(archive, project.root / "project.json", "project.json")
        _write_tree(archive, project.root / "subtitles", "subtitles")
        for optional_name in ("style.json", "glossary.json", "approvals.json"):
            optional = project.root / optional_name
            if optional.is_file():
                _write_file(archive, optional, optional_name)
        if mode in {ProjectPackageMode.PORTABLE, ProjectPackageMode.ARCHIVE}:
            _write_tree(archive, project.root / "source", "source", store=True)
        if mode is ProjectPackageMode.ARCHIVE:
            _write_tree(archive, project.root / "cache", "cache", store=True)
    temp.replace(output)
    return output


def import_project_package(
    package_path: str | Path,
    destination_root: str | Path,
    *,
    source_override: str | Path | None = None,
) -> Project:
    package = Path(package_path)
    if not package.is_file():
        raise FileNotFoundError(package)
    destination = Path(destination_root).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"project directory is not empty: {destination}")
    created_destination = not destination.exists()
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(package) as archive:
            _validate_archive_paths(archive)
            try:
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            except KeyError as exc:
                raise ValueError("project package is missing manifest.json") from exc
            _validate_manifest(manifest)
            if "project.json" not in archive.namelist():
                raise ValueError("project package is missing project.json")
            archive.extractall(destination)

        project_payload = json.loads((destination / "project.json").read_text(encoding="utf-8"))
        if not isinstance(project_payload, dict):
            raise ValueError("project.json must contain an object")
        source_relative = PurePosixPath(str(project_payload.get("source_path") or ""))
        if source_relative.is_absolute() or ".." in source_relative.parts or not source_relative.parts:
            raise ValueError("project package has unsafe source_path")
        source_target = destination.joinpath(*source_relative.parts)
        if not source_target.is_file():
            if source_override is None:
                raise FileNotFoundError("lightweight project package requires source_override to relink the source video")
            source = Path(source_override)
            if not source.is_file():
                raise FileNotFoundError(source)
            source_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, source_target)

        _ensure_project_dirs(destination)
        return ProjectService().open(destination)
    except Exception:
        if created_destination:
            shutil.rmtree(destination, ignore_errors=True)
        raise


def _validate_manifest(manifest: object) -> None:
    if not isinstance(manifest, dict):
        raise ValueError("project package manifest must be an object")
    if manifest.get("format") != PACKAGE_FORMAT:
        raise ValueError("not a SubReplace project package")
    if manifest.get("version") != PACKAGE_VERSION:
        raise ValueError(f"unsupported project package version: {manifest.get('version')}")
    try:
        ProjectPackageMode(str(manifest.get("mode")))
    except ValueError as exc:
        raise ValueError("invalid project package mode") from exc


def _validate_archive_paths(archive: zipfile.ZipFile) -> None:
    for info in archive.infolist():
        normalized = info.filename.replace("\\", "/")
        path = PurePosixPath(normalized)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"unsafe package path: {info.filename}")
        mode = (info.external_attr >> 16) & 0o170000
        if mode == 0o120000:
            raise ValueError(f"unsafe package path: symlink {info.filename}")


def _write_file(archive: zipfile.ZipFile, path: Path, arcname: str, *, store: bool = False) -> None:
    if not path.is_file():
        return
    archive.write(path, arcname=arcname, compress_type=zipfile.ZIP_STORED if store else zipfile.ZIP_DEFLATED)


def _write_tree(archive: zipfile.ZipFile, root: Path, prefix: str, *, store: bool = False) -> None:
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*")):
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            _write_file(archive, path, f"{prefix}/{relative}", store=store)


def _ensure_project_dirs(root: Path) -> None:
    for path in (
        root / "source",
        root / "subtitles",
        root / "exports",
        root / "jobs",
    ):
        path.mkdir(parents=True, exist_ok=True)
    from .service import CACHE_DIRS
    for name in CACHE_DIRS:
        (root / "cache" / name).mkdir(parents=True, exist_ok=True)
