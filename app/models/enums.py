from __future__ import annotations

from enum import Enum


class TextType(str, Enum):
    DIALOGUE_SUBTITLE = "dialogue_subtitle"
    WATERMARK = "watermark"
    LOGO = "logo"
    TITLE = "title"
    SCENE_TEXT = "scene_text"
    UI_TEXT = "ui_text"
    DECORATION = "decoration"
    UNKNOWN = "unknown"


class ReviewStatus(str, Enum):
    AUTO = "auto"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReconstructionQuality(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    FAILED = "failed"


class ProjectState(str, Enum):
    NEW = "new"
    ANALYZING = "analyzing"
    DETECTING = "detecting"
    TRANSCRIBING = "transcribing"
    RECONCILING = "reconciling"
    TRANSLATING = "translating"
    ERASING = "erasing"
    RENDERING = "rendering"
    READY_FOR_REVIEW = "ready_for_review"
    READY_FOR_EXPORT = "ready_for_export"
    COMPLETED = "completed"
    FAILED = "failed"


ERASABLE_TYPES = frozenset({TextType.DIALOGUE_SUBTITLE})
