from __future__ import annotations

import importlib.util
import os
import shutil
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

from app.core.media.ffmpeg import FFmpegMedia


class CheckStatus(str, Enum):
    PASS = "pass"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CudaStatus:
    available: bool
    device_name: str | None
    vram_mb: int


@dataclass(frozen=True, slots=True)
class PreflightCheck:
    name: str
    status: CheckStatus
    message: str


@dataclass(frozen=True, slots=True)
class PreflightReport:
    checks: tuple[PreflightCheck, ...]

    def by_name(self, name: str) -> PreflightCheck:
        for item in self.checks:
            if item.name == name:
                return item
        raise KeyError(name)

    @property
    def has_failures(self) -> bool:
        return any(item.status is CheckStatus.FAILED for item in self.checks)


class PreflightService:
    def __init__(
        self,
        *,
        binary_lookup: Callable[[str], str | None] = shutil.which,
        cuda_probe: Callable[[], CudaStatus] | None = None,
        pyside_probe: Callable[[], bool] | None = None,
        disk_probe: Callable[[Path], int] | None = None,
        decode_probe: Callable[[Path], tuple[bool, str]] | None = None,
    ) -> None:
        self.binary_lookup = binary_lookup
        self.cuda_probe = cuda_probe or self._probe_cuda
        self.pyside_probe = pyside_probe or (lambda: importlib.util.find_spec("PySide6") is not None)
        self.disk_probe = disk_probe or (lambda path: shutil.disk_usage(path).free)
        self.decode_probe = decode_probe or self._probe_decode

    def check(self, *, work_dir: str | Path, source_path: str | Path | None = None, require_desktop: bool = True) -> PreflightReport:
        work = Path(work_dir)
        work.mkdir(parents=True, exist_ok=True)
        checks: list[PreflightCheck] = []
        for binary in ("ffmpeg", "ffprobe"):
            resolved = self.binary_lookup(binary)
            checks.append(
                PreflightCheck(
                    binary,
                    CheckStatus.PASS if resolved else CheckStatus.FAILED,
                    resolved or f"{binary} not found on PATH",
                )
            )
        cuda = self.cuda_probe()
        checks.append(
            PreflightCheck(
                "cuda",
                CheckStatus.PASS if cuda.available else CheckStatus.DEGRADED,
                cuda.device_name or "CUDA unavailable; CPU-capable stages remain available",
            )
        )
        checks.append(
            PreflightCheck(
                "vram",
                CheckStatus.PASS if cuda.vram_mb >= 8192 else CheckStatus.DEGRADED,
                f"{cuda.vram_mb} MB detected; 8192 MB is the baseline for video AI inpainting",
            )
        )
        free = int(self.disk_probe(work))
        checks.append(
            PreflightCheck(
                "free_disk",
                CheckStatus.PASS if free >= 2 * 1024**3 else CheckStatus.FAILED,
                f"{free / 1024**3:.1f} GiB free",
            )
        )
        checks.append(self._write_check(work))
        if require_desktop:
            pyside_available = self.pyside_probe()
            checks.append(
                PreflightCheck(
                    "pyside6",
                    CheckStatus.PASS if pyside_available else CheckStatus.FAILED,
                    "PySide6 available" if pyside_available else "PySide6 is not installed; install the desktop optional dependency",
                )
            )
        if source_path is not None:
            source = Path(source_path)
            ok, message = self.decode_probe(source)
            checks.append(PreflightCheck("decode", CheckStatus.PASS if ok else CheckStatus.FAILED, message))
        return PreflightReport(tuple(checks))

    @staticmethod
    def _write_check(work: Path) -> PreflightCheck:
        try:
            with tempfile.NamedTemporaryFile(dir=work, prefix=".subreplace-write-", delete=True) as handle:
                handle.write(b"ok")
                handle.flush()
            return PreflightCheck("write_permission", CheckStatus.PASS, f"Writable: {work}")
        except OSError as exc:
            return PreflightCheck("write_permission", CheckStatus.FAILED, f"Not writable: {exc}")

    @staticmethod
    def _probe_cuda() -> CudaStatus:
        try:
            import torch
        except ImportError:
            return CudaStatus(False, None, 0)
        if not torch.cuda.is_available():
            return CudaStatus(False, None, 0)
        try:
            properties = torch.cuda.get_device_properties(0)
            return CudaStatus(True, str(properties.name), int(properties.total_memory // (1024**2)))
        except Exception:
            return CudaStatus(True, "CUDA device", 0)

    @staticmethod
    def _probe_decode(path: Path) -> tuple[bool, str]:
        try:
            metadata = FFmpegMedia().probe(path)
        except Exception as exc:
            return False, str(exc)
        return True, f"{metadata.width}x{metadata.height} @ {metadata.fps:.3f} fps"
