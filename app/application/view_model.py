from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shlex

from app.application.session import StudioSession
from app.core.preflight import CheckStatus, PreflightCheck, PreflightReport, PreflightService
from app.core.media.ffmpeg import FFmpegMedia
from app.providers.inpainting.propainter import ProPainterProvider
from app.providers.inpainting.e2fgvi import E2FGVIProvider
import importlib.util


class PreflightFailedError(RuntimeError):
    def __init__(self, report: PreflightReport) -> None:
        super().__init__("preflight checks failed")
        self.report = report


@dataclass(frozen=True, slots=True)
class ProjectStartRequest:
    source_path: str
    project_root: str
    project_name: str
    target_language: str = "vi"
    translation_provider: str = "openai"
    translation_model: str = ""
    endpoint: str = ""
    api_key: str = ""
    local_command: str = ""
    temporal_provider: str = "classical"
    temporal_repo_dir: str = ""
    temporal_checkpoint: str = ""
    fp16: bool = True


class StudioViewModel:
    def __init__(
        self,
        *,
        session: StudioSession | None = None,
        preflight: PreflightService | None = None,
        media: FFmpegMedia | None = None,
        module_probe=None,
        temporal_validator=None,
        require_desktop: bool = True,
    ) -> None:
        self.session = session or StudioSession()
        self.preflight = preflight or PreflightService()
        self.media = media or FFmpegMedia()
        self.module_probe = module_probe or self._default_module_probe
        self.temporal_validator = temporal_validator or self._validate_temporal_runtime
        self.require_desktop = bool(require_desktop)

    @staticmethod
    def _validate_temporal_runtime(config: dict[str, object] | None) -> None:
        if not config:
            return
        provider = str(config.get("provider") or "").lower()
        if provider == "propainter":
            ProPainterProvider(repo_dir=str(config.get("repo_dir") or ""))
            return
        if provider == "e2fgvi":
            E2FGVIProvider(
                repo_dir=str(config.get("repo_dir") or ""),
                checkpoint=str(config.get("checkpoint") or ""),
            )
            return
        raise ValueError(f"unsupported temporal provider: {provider}")

    @staticmethod
    def _default_module_probe(name: str) -> bool:
        try:
            return importlib.util.find_spec(name) is not None
        except (ImportError, ModuleNotFoundError, AttributeError):
            return False

    def _runtime_checks(self, request: ProjectStartRequest, *, has_audio: bool) -> tuple[PreflightCheck, ...]:
        required = [("paddleocr", "PaddleOCR is required for Chinese text recognition")]
        if has_audio:
            required.append(("faster_whisper", "faster-whisper is required when the source has audio"))
        provider = request.translation_provider.strip().lower()
        if provider == "openai":
            required.append(("openai", "OpenAI SDK is required for the selected translation provider"))
        elif provider == "gemini":
            required.append(("google.genai", "google-genai is required for the selected translation provider"))
        checks = []
        for module, message in required:
            available = bool(self.module_probe(module))
            checks.append(PreflightCheck(
                module.replace(".", "_"),
                CheckStatus.PASS if available else CheckStatus.FAILED,
                "available" if available else message,
            ))
        return tuple(checks)

    def _translation_config(self, request: ProjectStartRequest) -> dict[str, object]:
        provider = request.translation_provider.strip().lower()
        config: dict[str, object] = {"translation_provider": provider}
        if request.translation_model.strip():
            config["model"] = request.translation_model.strip()
        if request.api_key:
            config["api_key"] = request.api_key
        if provider == "custom":
            if not request.endpoint.strip():
                raise ValueError("custom translation provider requires endpoint")
            config["endpoint"] = request.endpoint.strip()
        elif provider == "local":
            command = shlex.split(request.local_command)
            if not command:
                raise ValueError("local translation provider requires a command")
            config["command"] = command
        elif provider not in {"openai", "gemini"}:
            raise ValueError("translation provider must be one of: openai, gemini, custom, local")
        return config

    def _temporal_config(self, request: ProjectStartRequest) -> dict[str, object] | None:
        provider = request.temporal_provider.strip().lower()
        if provider in {"", "classical"}:
            return None
        if provider == "propainter":
            if not request.temporal_repo_dir.strip():
                raise ValueError("ProPainter requires an installed repository folder")
            return {
                "provider": "propainter",
                "repo_dir": request.temporal_repo_dir.strip(),
                "fp16": bool(request.fp16),
            }
        if provider == "e2fgvi":
            if not request.temporal_repo_dir.strip() or not request.temporal_checkpoint.strip():
                raise ValueError("E2FGVI requires repository folder and checkpoint")
            return {
                "provider": "e2fgvi",
                "repo_dir": request.temporal_repo_dir.strip(),
                "checkpoint": request.temporal_checkpoint.strip(),
                "fp16": bool(request.fp16),
            }
        raise ValueError("temporal provider must be one of: classical, propainter, e2fgvi")

    def start(self, request: ProjectStartRequest, *, on_progress=None):
        source = Path(request.source_path).resolve()
        root = Path(request.project_root).resolve()
        report = self.preflight.check(work_dir=root.parent, source_path=source, require_desktop=self.require_desktop)
        if report.has_failures:
            raise PreflightFailedError(report)
        has_audio = bool(self.media.probe(source).has_audio)
        runtime_checks = self._runtime_checks(request, has_audio=has_audio)
        report = PreflightReport(tuple(report.checks) + runtime_checks)
        if report.has_failures:
            raise PreflightFailedError(report)
        translation_config = self._translation_config(request)
        temporal_config = self._temporal_config(request)
        self.temporal_validator(temporal_config)
        project = self.session.create_project(
            source_path=source,
            project_root=root,
            name=request.project_name.strip() or source.stem,
            target_language=request.target_language,
        )
        handle = self.session.start_full(
            project,
            translation_config=translation_config,
            temporal_config=temporal_config,
            on_progress=on_progress,
            has_audio=has_audio,
        )
        return handle, report
