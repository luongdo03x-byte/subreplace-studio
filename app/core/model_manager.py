from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from app.core.components.manifest import ComponentManifest
from app.core.components.store import ComponentStore
from app.core.licenses import ProviderMetadata, default_provider_registry
from app.providers.inpainting.external_plugin import LicenseAcceptanceStore


@dataclass(frozen=True, slots=True)
class ModelStatus:
    name: str
    version: str
    license_name: str
    commercial_use_allowed: bool | None
    weights_bundled: bool
    user_install_required: bool
    installed: bool
    plugin_path: Path | None
    license_accepted: bool
    component_id: str | None = None
    component_version: str | None = None
    min_vram_mb: int | None = None
    component_path: Path | None = None


class ModelManagerService:
    def __init__(
        self,
        *,
        model_root: str | Path,
        plugin_paths: Mapping[str, str | Path] | None = None,
        component_manifests: Mapping[str, ComponentManifest] | None = None,
    ) -> None:
        self.model_root = Path(model_root)
        self.plugin_paths = {name: Path(path) for name, path in (plugin_paths or {}).items()}
        self.component_manifests = dict(component_manifests or {})
        self.component_store = ComponentStore(self.model_root / "components")
        self.registry = {item.name: item for item in default_provider_registry()}

    def list_models(self) -> tuple[ModelStatus, ...]:
        return tuple(self._status(meta) for meta in self.registry.values())

    def _status(self, meta: ProviderMetadata) -> ModelStatus:
        plugin_path = self.plugin_paths.get(meta.name)
        manifest = self.component_manifests.get(meta.name)
        component_path = self.component_store.active_path(manifest.id) if manifest else None
        component_version = self.component_store.active_version(manifest.id) if manifest else None
        if meta.user_install_required:
            installed = bool(plugin_path and plugin_path.is_dir())
        elif manifest is not None:
            installed = component_path is not None and component_version == manifest.version
        else:
            installed = meta.weights_bundled
        accepted = self._is_accepted(meta, plugin_path)
        return ModelStatus(
            name=meta.name,
            version=meta.version,
            license_name=meta.license_name,
            commercial_use_allowed=meta.commercial_use_allowed,
            weights_bundled=meta.weights_bundled,
            user_install_required=meta.user_install_required,
            installed=installed,
            plugin_path=plugin_path,
            license_accepted=accepted,
            component_id=manifest.id if manifest else None,
            component_version=component_version,
            min_vram_mb=manifest.min_vram_mb if manifest else None,
            component_path=component_path,
        )

    def _meta(self, provider: str) -> ProviderMetadata:
        try:
            return self.registry[provider]
        except KeyError as exc:
            raise KeyError(f"unknown model provider: {provider}") from exc

    @staticmethod
    def _is_accepted(meta: ProviderMetadata, plugin_path: Path | None) -> bool:
        if not meta.user_install_required:
            return True
        if plugin_path is None or not plugin_path.is_dir():
            return False
        return LicenseAcceptanceStore(plugin_path).is_accepted(meta.name, meta.license_name, meta.version)

    def is_license_accepted(self, provider: str) -> bool:
        meta = self._meta(provider)
        return self._is_accepted(meta, self.plugin_paths.get(provider))

    def accept_license(self, provider: str) -> None:
        meta = self._meta(provider)
        if not meta.user_install_required:
            return
        plugin_path = self.plugin_paths.get(provider)
        if plugin_path is None or not plugin_path.is_dir():
            raise FileNotFoundError(f"select an installed {provider} plugin folder before accepting its license")
        LicenseAcceptanceStore(plugin_path).accept(meta.name, meta.license_name, meta.version)
