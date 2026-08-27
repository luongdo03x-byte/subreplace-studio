from __future__ import annotations

from pathlib import Path

from app.core.model_manager import ModelManagerService
from app.core.settings import SettingsStore, app_data_root


class ModelManagerController:
    def __init__(
        self,
        *,
        settings_store: SettingsStore | None = None,
        model_root: str | Path | None = None,
    ) -> None:
        self.settings_store = settings_store or SettingsStore()
        self.model_root = Path(model_root) if model_root is not None else app_data_root() / "models"

    def service(self) -> ModelManagerService:
        settings = self.settings_store.load()
        return ModelManagerService(model_root=self.model_root, plugin_paths=settings.plugin_paths)

    def list_models(self):
        return self.service().list_models()

    def set_plugin_path(self, provider: str, path: str | Path) -> None:
        candidate = Path(path).expanduser().resolve()
        if not candidate.is_dir():
            raise FileNotFoundError(candidate)
        self.settings_store.set_plugin_path(provider, candidate)

    def accept_license(self, provider: str) -> None:
        self.service().accept_license(provider)

    def plugin_path(self, provider: str) -> Path | None:
        value = self.settings_store.load().plugin_paths.get(provider)
        return Path(value) if value else None
