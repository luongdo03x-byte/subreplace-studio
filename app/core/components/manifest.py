from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from typing import Any, Mapping

_COMPONENT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def _safe_relative(value: str, *, label: str) -> str:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if not value or path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ValueError(f"unsafe {label}: {value!r}")
    return normalized


def _sha(value: object, *, label: str) -> str:
    text = str(value)
    if not _SHA256.fullmatch(text):
        raise ValueError(f"invalid {label} SHA-256")
    return text.lower()


@dataclass(frozen=True, slots=True)
class ComponentLicense:
    name: str
    commercial_use_allowed: bool | None
    requires_acceptance: bool

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ComponentLicense":
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("license name is required")
        commercial = payload.get("commercial_use_allowed")
        if commercial not in {True, False, None}:
            raise ValueError("commercial_use_allowed must be true, false, or null")
        return cls(name, commercial, bool(payload.get("requires_acceptance", False)))


@dataclass(frozen=True, slots=True)
class ComponentPart:
    name: str
    url: str
    size: int
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _safe_relative(self.name, label="part name"))
        if "/" in self.name:
            raise ValueError(f"unsafe part name: {self.name!r}")
        if not self.url.strip():
            raise ValueError("component part URL is required")
        if self.size < 0:
            raise ValueError("component part size must be non-negative")
        object.__setattr__(self, "sha256", _sha(self.sha256, label="part"))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ComponentPart":
        return cls(
            name=str(payload.get("name") or ""),
            url=str(payload.get("url") or ""),
            size=int(payload.get("size", -1)),
            sha256=str(payload.get("sha256") or ""),
        )


@dataclass(frozen=True, slots=True)
class ComponentManifest:
    id: str
    version: str
    min_vram_mb: int
    size: int
    sha256: str
    parts: tuple[ComponentPart, ...]
    license: ComponentLicense
    bundled: bool
    entrypoint: str

    def __post_init__(self) -> None:
        if not _COMPONENT_ID.fullmatch(self.id):
            raise ValueError(f"invalid component id: {self.id!r}")
        if not _VERSION.fullmatch(self.version):
            raise ValueError(f"invalid component version: {self.version!r}")
        if self.min_vram_mb < 0:
            raise ValueError("min_vram_mb must be non-negative")
        if self.size < 0:
            raise ValueError("component size must be non-negative")
        object.__setattr__(self, "sha256", _sha(self.sha256, label="archive"))
        if not self.parts:
            raise ValueError("component manifest requires at least one part")
        object.__setattr__(self, "entrypoint", _safe_relative(self.entrypoint, label="entrypoint"))
        if self.bundled and self.license.commercial_use_allowed is not True:
            raise ValueError("bundled components must explicitly allow commercial use")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ComponentManifest":
        parts_payload = payload.get("parts")
        if not isinstance(parts_payload, list):
            raise ValueError("component parts must be a list")
        license_payload = payload.get("license")
        if not isinstance(license_payload, Mapping):
            raise ValueError("component license must be an object")
        return cls(
            id=str(payload.get("id") or ""),
            version=str(payload.get("version") or ""),
            min_vram_mb=int(payload.get("min_vram_mb", 0)),
            size=int(payload.get("size", -1)),
            sha256=str(payload.get("sha256") or ""),
            parts=tuple(ComponentPart.from_dict(item) for item in parts_payload if isinstance(item, Mapping)),
            license=ComponentLicense.from_dict(license_payload),
            bundled=bool(payload.get("bundled", False)),
            entrypoint=str(payload.get("entrypoint") or ""),
        )
