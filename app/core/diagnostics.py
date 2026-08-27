from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import platform
import shutil
import sys
from pathlib import Path

from app.core.project.migrations import CURRENT_PROJECT_SCHEMA_VERSION


def _package_status(module: str, distribution: str | None = None) -> dict[str, object]:
    installed = importlib.util.find_spec(module) is not None
    version = None
    if installed:
        try:
            version = importlib.metadata.version(distribution or module)
        except importlib.metadata.PackageNotFoundError:
            version = "unknown"
    return {"installed": installed, "version": version}


def _cuda_status() -> dict[str, object]:
    try:
        import torch
    except ImportError:
        return {"available": False, "device_name": None, "vram_mb": 0}
    if not torch.cuda.is_available():
        return {"available": False, "device_name": None, "vram_mb": 0}
    try:
        props = torch.cuda.get_device_properties(0)
        return {
            "available": True,
            "device_name": str(props.name),
            "vram_mb": int(props.total_memory // (1024**2)),
        }
    except Exception:
        return {"available": True, "device_name": "CUDA device", "vram_mb": 0}


def collect_diagnostics(*, model_manager=None, project=None, job_store=None) -> dict[str, object]:
    """Collect shareable runtime metadata without reading environment values or credentials."""
    report: dict[str, object] = {
        "python": {"version": platform.python_version(), "executable": Path(sys.executable).name},
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "binaries": {name: bool(shutil.which(name)) for name in ("ffmpeg", "ffprobe")},
        "optional_dependencies": {
            "PySide6": _package_status("PySide6"),
            "torch": _package_status("torch"),
            "paddleocr": _package_status("paddleocr"),
            "faster_whisper": _package_status("faster_whisper", "faster-whisper"),
            "av": _package_status("av"),
            "openai": _package_status("openai"),
            "google_genai": _package_status("google.genai", "google-genai"),
        },
        "cuda": _cuda_status(),
        "project_schema": CURRENT_PROJECT_SCHEMA_VERSION,
    }
    if model_manager is not None:
        report["components"] = [
            {
                "name": item.name,
                "provider_version": item.version,
                "installed": item.installed,
                "license": item.license_name,
                "commercial_use_allowed": item.commercial_use_allowed,
                "license_accepted": item.license_accepted,
                "component_id": item.component_id,
                "component_version": item.component_version,
                "min_vram_mb": item.min_vram_mb,
            }
            for item in model_manager.list_models()
        ]
    if project is not None:
        report["project"] = {
            "id": project.id,
            "name": project.name,
            "target_language": project.target_language,
            "state": project.state.value,
            "completed_stages": sorted(project.completed_stages),
            "schema_version": CURRENT_PROJECT_SCHEMA_VERSION,
        }
    if job_store is not None:
        report["jobs"] = [
            {
                "id": item.id,
                "stage": item.stage,
                "status": item.status.value,
                "attempts": item.attempts,
                "progress": item.progress,
                "has_error": item.error is not None,
                "completed_stages": list(item.completed_stages),
            }
            for item in job_store.list_recent(limit=20)
        ]
    return report


def write_diagnostics(path: str | Path, **context) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(collect_diagnostics(**context), indent=2, ensure_ascii=False), encoding="utf-8")
    return target
