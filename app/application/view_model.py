from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shlex

from app.application.session import StudioSession
from app.core.preflight import CheckStatus, PreflightCheck, PreflightReport, PreflightService
from app.core.media.ffmpeg import FFmpegMedia
from app.providers.inpainting.propainter import ProPainterProvider
from app.providers.inpainting.e2fgvi import E2FGVIProvider
from app.providers.tts.edge import VOICE_FEMALE, VOICE_MALE
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
    erase_subtitles: bool = False
    dub_enabled: bool = True
    dub_voice_female: str = VOICE_FEMALE
    dub_voice_male: str = VOICE_MALE
    dub_default_gender: str = "female"
    dub_rate: str = "+0%"
    duck_ratio: int = 12


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
        if request.dub_enabled:
            required.append(("edge_tts", "edge-tts is required for Vietnamese dubbing"))
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

    _DUB_RATE_PATTERN = re.compile(r"^[+-]\d+%$")

    def _dub_config(self, request: ProjectStartRequest) -> dict[str, object] | None:
        if not request.dub_enabled:
            return None
        female = request.dub_voice_female.strip()
        male = request.dub_voice_male.strip()
        if not female or not male:
            raise ValueError("dubbing requires both a female and a male voice id")
        if request.dub_default_gender not in {"female", "male"}:
            raise ValueError("dub_default_gender must be 'female' or 'male'")
        if request.duck_ratio <= 0:
            raise ValueError("duck_ratio must be positive")
        rate = request.dub_rate.strip() or "+0%"
        # edge-tts takes this string as-is; a malformed value (e.g. "20"
        # instead of "+20%") is only discovered after ~800 lines of retry
        # backoff, so reject it here instead.
        if not self._DUB_RATE_PATTERN.fullmatch(rate):
            raise ValueError(f"dub_rate must look like '+20%' or '-10%' (got {rate!r})")
        return {
            "voice_female": female,
            "voice_male": male,
            "default_gender": request.dub_default_gender,
            "rate": rate,
            "duck_ratio": int(request.duck_ratio),
        }

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
        # Validating a temporal plugin the user is not going to run would block
        # the common no-erase path for no reason.
        temporal_config = self._temporal_config(request) if request.erase_subtitles else None
        if temporal_config is not None:
            self.temporal_validator(temporal_config)
        dub_config = self._dub_config(request)
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
            erase_enabled=request.erase_subtitles,
            dub_config=dub_config,
        )
        return handle, report
