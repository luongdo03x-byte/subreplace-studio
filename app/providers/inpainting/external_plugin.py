from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np


class PluginValidationError(RuntimeError):
    pass


class LicenseNotAcceptedError(PluginValidationError):
    pass


class PluginExecutionError(RuntimeError):
    pass


@dataclass(slots=True)
class LicenseAcceptanceStore:
    root: Path

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    @property
    def path(self) -> Path:
        return self.root / ".subreplace" / "license-acceptance.json"

    def _read(self) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PluginValidationError(f"invalid license acceptance file: {self.path}") from exc
        if not isinstance(value, list):
            raise PluginValidationError(f"invalid license acceptance file: {self.path}")
        return [entry for entry in value if isinstance(entry, dict)]

    def is_accepted(self, provider: str, license_name: str, version: str) -> bool:
        needle = (provider, license_name, version)
        return any(
            (entry.get("provider"), entry.get("license"), entry.get("version")) == needle
            for entry in self._read()
        )

    def accept(self, provider: str, license_name: str, version: str) -> None:
        entries = self._read()
        if self.is_accepted(provider, license_name, version):
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        entries.append(
            {
                "provider": provider,
                "license": license_name,
                "version": version,
                "accepted_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self.path.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def require_files(root: Path, relative_paths: Sequence[str]) -> None:
    missing = [item for item in relative_paths if not (root / item).is_file()]
    if missing:
        raise PluginValidationError(
            f"missing user-installed plugin files under {root}: {', '.join(missing)}"
        )


def require_license(
    root: Path,
    *,
    provider: str,
    license_name: str,
    version: str,
) -> None:
    if not LicenseAcceptanceStore(root).is_accepted(provider, license_name, version):
        raise LicenseNotAcceptedError(
            f"license not accepted for {provider} {version} ({license_name}); "
            "accept it explicitly in Model Manager before running the provider"
        )


def write_video(path: Path, frames: Sequence[np.ndarray], fps: float) -> None:
    if not frames:
        raise PluginValidationError("cannot invoke inpainting plugin with zero frames")
    h, w = frames[0].shape[:2]
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), float(fps), (w, h))
    if not writer.isOpened():
        raise PluginExecutionError(f"failed to open temporary video writer: {path}")
    for frame in frames:
        if frame.shape[:2] != (h, w):
            writer.release()
            raise PluginValidationError("all plugin frames must have identical dimensions")
        writer.write(frame)
    writer.release()


def write_mask_directory(path: Path, masks: Sequence[np.ndarray]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for index, mask in enumerate(masks):
        binary = (mask > 0).astype(np.uint8) * 255
        if not cv2.imwrite(str(path / f"{index:05d}.png"), binary):
            raise PluginExecutionError(f"failed to write mask frame {index}")


def read_video(path: Path, expected_frames: int) -> tuple[np.ndarray, ...]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise PluginExecutionError(f"plugin did not produce a readable video: {path}")
    frames: list[np.ndarray] = []
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        frames.append(frame)
    capture.release()
    if len(frames) != expected_frames:
        raise PluginExecutionError(
            f"plugin output frame count mismatch: expected {expected_frames}, got {len(frames)}"
        )
    return tuple(frames)


def run_checked(command: Sequence[str], *, cwd: Path, timeout_seconds: int = 3600) -> str:
    proc = subprocess.run(
        list(command),
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout)[-4000:]
        raise PluginExecutionError(
            f"plugin process failed with exit {proc.returncode}: {' '.join(command[:3])}\n{tail}"
        )
    return proc.stdout


def temporary_workspace(prefix: str):
    return tempfile.TemporaryDirectory(prefix=prefix)
