from __future__ import annotations

from enum import Enum


class ChangeType(str, Enum):
    SOURCE = "source"
    OCR_EDIT = "ocr_edit"
    TRANSLATION_EDIT = "translation_edit"
    GLOSSARY = "glossary"
    STYLE = "style"


class CacheGraph:
    STAGES = (
        "analysis",
        "detection",
        "ocr",
        "asr",
        "reconciliation",
        "masks",
        "erasing",
        "translation",
        "render",
    )

    _INVALIDATION = {
        ChangeType.SOURCE: STAGES,
        ChangeType.OCR_EDIT: ("reconciliation", "translation", "render"),
        ChangeType.TRANSLATION_EDIT: ("render",),
        ChangeType.GLOSSARY: ("translation", "render"),
        ChangeType.STYLE: ("render",),
    }

    def invalidated_by(self, change: ChangeType) -> tuple[str, ...]:
        return tuple(self._INVALIDATION[change])

    def apply(self, completed_stages: set[str], change: ChangeType) -> set[str]:
        invalid = set(self.invalidated_by(change))
        return {stage for stage in completed_stages if stage not in invalid}
