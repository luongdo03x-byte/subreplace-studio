from __future__ import annotations

from app.core.languages import TARGET_LANGUAGE_CODES

from dataclasses import dataclass, field
from pathlib import Path

from .enums import ProjectState


@dataclass(slots=True)
class Project:
    id: str
    name: str
    root: Path
    source_path: Path
    target_language: str
    state: ProjectState = ProjectState.NEW
    glossary: dict[str, str] = field(default_factory=dict)
    completed_stages: set[str] = field(default_factory=set)
    subtitle_edits: dict[str, str] = field(default_factory=dict)
    approvals: set[str] = field(default_factory=set)
    settings: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.target_language not in TARGET_LANGUAGE_CODES:
            raise ValueError(f"Unsupported target language: {self.target_language}")
