from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Callable
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen
import zipfile

from .manifest import ComponentManifest, ComponentPart
from .store import ComponentStore


class InstallState(str, Enum):
    IDLE = "idle"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    EXTRACTING = "extracting"
    READY = "ready"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class InstallProgress:
    state: InstallState
    received: int
    total: int
    version: str
    message: str = ""


class ComponentInstaller:
    def __init__(self, store: ComponentStore) -> None:
        self.store = store

    def install(
        self,
        manifest: ComponentManifest,
        *,
        on_progress: Callable[[InstallProgress], None] | None = None,
    ) -> Path:
        emit = on_progress or (lambda _progress: None)
        downloads = self.store.downloads_dir(manifest.id, manifest.version)
        downloads.mkdir(parents=True, exist_ok=True)
        received = 0
        part_paths: list[Path] = []
        staging: Path | None = None
        try:
            for part in manifest.parts:
                target = downloads / part.name
                delta = self._download_part(part, target)
                received += delta
                emit(InstallProgress(InstallState.DOWNLOADING, received, manifest.size, manifest.version, part.name))
                emit(InstallProgress(InstallState.VERIFYING, received, manifest.size, manifest.version, part.name))
                if _hash_file(target) != part.sha256:
                    raise ValueError(f"checksum mismatch for component part {part.name}")
                part_paths.append(target)

            package = downloads / "component-package.zip"
            if len(part_paths) == 1:
                if part_paths[0].resolve() != package.resolve():
                    shutil.copyfile(part_paths[0], package)
            else:
                with package.open("wb") as output:
                    for part_path in part_paths:
                        with part_path.open("rb") as input_file:
                            shutil.copyfileobj(input_file, output, length=1024 * 1024)

            emit(InstallProgress(InstallState.VERIFYING, manifest.size, manifest.size, manifest.version, "archive"))
            if _hash_file(package) != manifest.sha256:
                raise ValueError("checksum mismatch for assembled component archive")

            component_root = self.store.component_root(manifest.id)
            component_root.mkdir(parents=True, exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix=f".staging-{manifest.version}-", dir=component_root))
            emit(InstallProgress(InstallState.EXTRACTING, manifest.size, manifest.size, manifest.version))
            _safe_extract_zip(package, staging)
            if not (staging / manifest.entrypoint).exists():
                raise ValueError(f"component entrypoint is missing: {manifest.entrypoint}")

            destination = self.store.version_dir(manifest.id, manifest.version)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                shutil.rmtree(staging, ignore_errors=True)
                staging = None
            else:
                staging.replace(destination)
                staging = None
            self.store.activate(manifest.id, manifest.version)
            shutil.rmtree(downloads, ignore_errors=True)
            emit(InstallProgress(InstallState.READY, manifest.size, manifest.size, manifest.version))
            return destination
        except Exception as exc:
            if staging is not None:
                shutil.rmtree(staging, ignore_errors=True)
            emit(InstallProgress(InstallState.ERROR, received, manifest.size, manifest.version, str(exc)))
            raise

    def _download_part(self, part: ComponentPart, target: Path) -> int:
        target.parent.mkdir(parents=True, exist_ok=True)
        parsed = urlparse(part.url)
        if parsed.scheme in {"", "file"}:
            source = Path(unquote(parsed.path)) if parsed.scheme == "file" else Path(part.url)
            if not source.is_file():
                raise FileNotFoundError(source)
            existing = target.stat().st_size if target.exists() else 0
            if existing > part.size:
                target.unlink()
                existing = 0
            with source.open("rb") as src:
                src.seek(existing)
                with target.open("ab" if existing else "wb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)
            final_size = target.stat().st_size
            if final_size != part.size:
                raise ValueError(f"component part size mismatch for {part.name}: {final_size}/{part.size}")
            return final_size

        if parsed.scheme not in {"http", "https"}:
            raise ValueError(f"unsupported component URL scheme: {parsed.scheme}")
        existing = target.stat().st_size if target.exists() else 0
        if existing > part.size:
            target.unlink()
            existing = 0
        headers = {"User-Agent": "SubReplace-Studio-Component-Manager"}
        if existing:
            headers["Range"] = f"bytes={existing}-"
        request = Request(part.url, headers=headers)
        with urlopen(request, timeout=30) as response:
            resume = existing > 0 and getattr(response, "status", None) == 206
            if existing and not resume:
                existing = 0
                target.unlink(missing_ok=True)
            mode = "ab" if resume else "wb"
            with target.open(mode) as output:
                shutil.copyfileobj(response, output, length=1024 * 1024)
        final_size = target.stat().st_size
        if final_size != part.size:
            raise ValueError(f"component part size mismatch for {part.name}: {final_size}/{part.size}")
        return final_size


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_extract_zip(archive_path: Path, destination: Path) -> None:
    root = destination.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            normalized = info.filename.replace("\\", "/")
            path = PurePosixPath(normalized)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"unsafe archive path: {info.filename}")
            # Unix symlink mode in ZipInfo external attributes.
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise ValueError(f"unsafe archive path: symlink {info.filename}")
            target = (destination / Path(*path.parts)).resolve()
            if target != root and root not in target.parents:
                raise ValueError(f"unsafe archive path: {info.filename}")
        archive.extractall(destination)
