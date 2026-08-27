from __future__ import annotations

from dataclasses import dataclass
import re

import numpy as np

from app.models.enums import ReviewStatus, TextType
from app.models.text_track import TextTrack


_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    text_type: TextType
    confidence: float
    margin: float
    review_status: ReviewStatus
    dialogue_score: float
    watermark_score: float


class TextClassifier:
    def __init__(self, *, confidence_threshold: float = 0.60, margin_threshold: float = 0.12) -> None:
        self.confidence_threshold = confidence_threshold
        self.margin_threshold = margin_threshold

    def classify(
        self,
        track: TextTrack,
        *,
        frame_size: tuple[int, int],
        total_frames: int,
        recognized_text: str = "",
        speech_overlap: float = 0.0,
        scene_count: int = 1,
        ocr_confidence: float = 0.0,
    ) -> ClassificationResult:
        width, height = frame_size
        if not track.bboxes:
            return ClassificationResult(TextType.UNKNOWN, 0.0, 0.0, ReviewStatus.NEEDS_REVIEW, 0.0, 0.0)
        centers_x = [(x + w / 2) / width for x, y, w, h in track.bboxes]
        centers_y = [(y + h / 2) / height for x, y, w, h in track.bboxes]
        cx, cy = float(np.median(centers_x)), float(np.median(centers_y))
        persistence = min(1.0, len(track.frame_indices) / max(total_frames, 1))
        text = recognized_text.strip()
        has_cjk = bool(_CJK_RE.search(text))
        has_handle = "@" in text or "http://" in text.lower() or "https://" in text.lower() or "www." in text.lower()
        looks_short_id = bool(text) and not has_cjk and len(text) <= 16
        near_edge = cx < 0.20 or cx > 0.80 or cy < 0.25
        centered = abs(cx - 0.5) <= 0.25
        bottom = cy >= 0.62

        dialogue = 0.0
        dialogue += 0.25 if has_cjk else 0.0
        dialogue += 0.25 if bottom else 0.0
        dialogue += 0.15 if centered else 0.0
        dialogue += 0.10 if persistence <= 0.45 else 0.0
        dialogue += 0.25 * float(np.clip(speech_overlap, 0.0, 1.0))

        watermark = 0.0
        watermark += 0.40 if has_handle else (0.12 if looks_short_id else 0.0)
        watermark += 0.20 if near_edge else 0.0
        watermark += 0.20 if persistence >= 0.60 else 0.0
        watermark += 0.10 if scene_count >= 2 else 0.0
        watermark += 0.10 if speech_overlap <= 0.15 else 0.0

        winner_type, winner = (
            (TextType.DIALOGUE_SUBTITLE, dialogue)
            if dialogue >= watermark
            else (TextType.WATERMARK, watermark)
        )
        loser = watermark if winner_type is TextType.DIALOGUE_SUBTITLE else dialogue
        margin = winner - loser
        if winner < self.confidence_threshold or margin < self.margin_threshold:
            return ClassificationResult(
                TextType.UNKNOWN,
                float(winner),
                float(margin),
                ReviewStatus.NEEDS_REVIEW,
                float(dialogue),
                float(watermark),
            )
        if winner_type is TextType.DIALOGUE_SUBTITLE:
            # Chinese dialogue subtitles always contain CJK glyphs. Latin-only
            # handle/id overlays (@accounts, short ids) drift across the frame
            # and must never be auto-approved as dialogue.
            if has_handle:
                return ClassificationResult(
                    TextType.WATERMARK,
                    float(max(winner, watermark)),
                    float(margin),
                    ReviewStatus.AUTO,
                    float(dialogue),
                    float(max(watermark, self.confidence_threshold)),
                )
            if not has_cjk:
                return ClassificationResult(
                    TextType.UNKNOWN,
                    float(winner),
                    float(margin),
                    ReviewStatus.NEEDS_REVIEW,
                    float(dialogue),
                    float(watermark),
                )
        if winner_type is TextType.DIALOGUE_SUBTITLE and ocr_confidence < 0.35:
            return ClassificationResult(
                TextType.UNKNOWN,
                float(winner),
                float(margin),
                ReviewStatus.NEEDS_REVIEW,
                float(dialogue),
                float(watermark),
            )
        review_status = (
            ReviewStatus.NEEDS_REVIEW
            if winner_type is TextType.DIALOGUE_SUBTITLE and ocr_confidence < 0.50
            else ReviewStatus.AUTO
        )
        return ClassificationResult(
            winner_type,
            float(winner),
            float(margin),
            review_status,
            float(dialogue),
            float(watermark),
        )
