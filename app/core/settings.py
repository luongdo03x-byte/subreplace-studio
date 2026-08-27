from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path


def app_data_root() -> Path:
    configured = os.environ.get("SUBREPLACE_APP_DATA", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        return (Path(base) if base else Path.home() / "AppData" / "Local") / "SubReplaceStudio"
    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    return base / "subreplace-studio"


@dataclass(frozen=True, slots=True)
class UserSettings:
    plugin_paths: dict[str, str] = field(default_factory=dict)


class SettingsStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else app_data_root() / "settings.json"

    def load(self) -> UserSettings:
        if not self.path.is_file():
            return UserSettings()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("settings must contain a JSON object")
        plugin_paths = payload.get("plugin_paths", {})
        if not isinstance(plugin_paths, dict):
            raise ValueError("settings.plugin_paths must be an object")
        return UserSettings({str(k): str(v) for k, v in plugin_paths.items()})

    def save(self, settings: UserSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(f".{self.path.name}.tmp")
        payload = {"plugin_paths": dict(sorted(settings.plugin_paths.items()))}
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)

    def set_plugin_path(self, provider: str, path: str | Path) -> UserSettings:
        name = str(provider).strip()
        if not name:
            raise ValueError("provider is required")
        resolved = Path(path).expanduser().resolve()
        current = self.load()
        updated = dict(current.plugin_paths)
        updated[name] = str(resolved)
        settings = UserSettings(updated)
        self.save(settings)
        return settings
