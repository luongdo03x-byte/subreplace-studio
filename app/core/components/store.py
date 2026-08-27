from __future__ import annotations

import json
from pathlib import Path

from .manifest import ComponentManifest


class ComponentStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def component_root(self, component_id: str) -> Path:
        ComponentManifest.__dataclass_fields__  # keep manifest module imported before path validation
        if not component_id or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-" for ch in component_id):
            raise ValueError(f"invalid component id: {component_id!r}")
        return self.root / component_id

    def version_dir(self, component_id: str, version: str) -> Path:
        if not version or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for ch in version):
            raise ValueError(f"invalid component version: {version!r}")
        return self.component_root(component_id) / "versions" / version

    def downloads_dir(self, component_id: str, version: str) -> Path:
        return self.component_root(component_id) / "downloads" / version

    def current_marker(self, component_id: str) -> Path:
        return self.component_root(component_id) / "current.json"

    def activate(self, component_id: str, version: str) -> None:
        version_dir = self.version_dir(component_id, version)
        if not version_dir.is_dir():
            raise FileNotFoundError(version_dir)
        marker = self.current_marker(component_id)
        marker.parent.mkdir(parents=True, exist_ok=True)
        temp = marker.with_suffix(".json.tmp")
        temp.write_text(json.dumps({"version": version}, indent=2) + "\n", encoding="utf-8")
        temp.replace(marker)

    def active_version(self, component_id: str) -> str | None:
        marker = self.current_marker(component_id)
        if not marker.is_file():
            return None
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        version = payload.get("version")
        if not isinstance(version, str):
            return None
        try:
            path = self.version_dir(component_id, version)
        except ValueError:
            return None
        return version if path.is_dir() else None

    def active_path(self, component_id: str) -> Path | None:
        version = self.active_version(component_id)
        return self.version_dir(component_id, version) if version else None
