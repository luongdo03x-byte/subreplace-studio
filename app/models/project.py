from __future__ import annotations

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
        if self.target_language not in {"vi", "en"}:
            raise ValueError("target_language must be 'vi' or 'en'")
