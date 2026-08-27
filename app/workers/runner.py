from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.providers.asr.faster_whisper import FasterWhisperProvider
from app.providers.ocr.paddle import PaddleOCRProvider
from app.core.eraser.inpainting_provider import InpaintingContext
from app.core.eraser.reconstruction import compose_inside_mask
from app.providers.inpainting.propainter import ProPainterProvider
from app.providers.inpainting.e2fgvi import E2FGVIProvider
from app.core.detection.morph_gradient import MorphGradientDetector
from app.core.media.ffmpeg import FFmpegMedia
from app.core.detection.classification import TextClassifier
from app.core.detection.recovery import recover_missing_events
from app.models.text_track import TextTrack
from app.core.eraser.mask_generator import generate_stroke_mask, temporal_stroke_mask
from app.core.eraser.pipeline import ClassicalEraser
from app.core.eraser.routing import HybridEraser
from app.core.translation.service import TranslationService
from app.core.translation.coalesce import coalesce_dialogue_events
from app.providers.translation.openai import OpenAITranslationProvider
from app.providers.translation.gemini import GeminiTranslationProvider
from app.providers.translation.custom import CustomAPITranslationProvider
from app.providers.translation.local import LocalCommandTranslationProvider
from app.models.subtitle import SubtitleSegment
from app.models.enums import TextType, ReviewStatus
from app.core.rendering.renderer import SubtitleRenderer
from app.core.rendering.style import SubtitleStyle
from app.core.ocr.events import TextEventScanner, select_representative_sample, fuse_event_ink, merge_fragmented_events
from .protocol import WorkerCommand, WorkerEvent, WorkerEventType


def _event(command: WorkerCommand, kind: WorkerEventType, progress: float, message: str = "", data: dict[str, Any] | None = None) -> WorkerEvent:
    return WorkerEvent(kind, command.job_id, command.stage, progress, message, data or {})


def _require_path(config: dict[str, Any], key: str) -> Path:
    value = str(config.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    path = Path(value).resolve()
    return path


def _project_path(command: WorkerCommand, key: str) -> Path:
    path = _require_path(command.config, key)
    root = Path(command.project_path).resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"{key} escapes project root: {path}")
    return path


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _run_ocr(command: WorkerCommand, dependencies: dict[str, Any]) -> tuple[WorkerEvent, ...]:
    config = command.config
    image_path = _project_path(command, "image_path")
    output_path = _project_path(command, "output_path")
    if not image_path.is_file():
        raise FileNotFoundError(image_path)
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"cannot decode image: {image_path}")
    raw_regions = config.get("regions")
    if not isinstance(raw_regions, list) or not raw_regions:
        raise ValueError("regions must be a non-empty array")
    regions: list[tuple[int, int, int, int]] = []
    for region in raw_regions:
        if not isinstance(region, (list, tuple)) or len(region) != 4:
            raise ValueError("each OCR region must contain x,y,w,h")
        regions.append(tuple(int(v) for v in region))
    engine = dependencies.get("ocr_engine")
    provider = PaddleOCRProvider(engine=engine) if engine is not None else PaddleOCRProvider()
    results = provider.recognize(image, regions, frame_index=int(config.get("frame_index", 0)))
    payload = [
        {"text": item.text, "confidence": float(item.confidence), "frame_index": int(item.frame_index)}
        for item in results
    ]
    _write_json(output_path, payload)
    return (
        _event(command, WorkerEventType.STARTED, 0.0, "OCR started"),
        _event(command, WorkerEventType.PROGRESS, 0.9, "OCR recognized", {"count": len(payload)}),
        _event(command, WorkerEventType.COMPLETED, 1.0, "OCR completed", {"output_path": str(output_path), "count": len(payload)}),
    )


def _run_asr(command: WorkerCommand, dependencies: dict[str, Any]) -> tuple[WorkerEvent, ...]:
    config = command.config
    audio_path = _project_path(command, "audio_path")
    output_path = _project_path(command, "output_path")
    if not audio_path.is_file():
        raise FileNotFoundError(audio_path)
    model = dependencies.get("whisper_model")
    provider = FasterWhisperProvider(
        model_size=str(config.get("model_size") or "small"),
        device=str(config.get("device") or "cpu"),
        compute_type=str(config["compute_type"]) if config.get("compute_type") else None,
        model=model,
    )
    segments = provider.transcribe(str(audio_path), language=str(config.get("language") or "zh"))
    payload = [
        {
            "start_ms": int(item.start_ms),
            "end_ms": int(item.end_ms),
            "text": item.text,
            "confidence": float(item.confidence),
        }
        for item in segments
    ]
    _write_json(output_path, payload)
    return (
        _event(command, WorkerEventType.STARTED, 0.0, "ASR started"),
        _event(command, WorkerEventType.PROGRESS, 0.9, "ASR transcribed", {"count": len(payload)}),
        _event(command, WorkerEventType.COMPLETED, 1.0, "ASR completed", {"output_path": str(output_path), "count": len(payload)}),
    )








def _build_translation_provider(config: dict[str, Any]):
    name = str(config.get("translation_provider") or config.get("provider") or "").strip().lower()
    if name == "openai":
        # OpenAI SDK reads OPENAI_API_KEY from the worker environment; keys are not persisted in job metadata.
        return OpenAITranslationProvider(model=str(config.get("model") or "gpt-5.6"), api_key=str(config["api_key"]) if config.get("api_key") else None)
    if name == "gemini":
        return GeminiTranslationProvider(model=str(config.get("model") or "gemini-2.5-flash"), api_key=str(config["api_key"]) if config.get("api_key") else None)
    if name == "custom":
        return CustomAPITranslationProvider(
            str(config.get("endpoint") or ""),
            api_key=str(config["api_key"]) if config.get("api_key") else None,
        )
    if name == "local":
        raw = config.get("command")
        if not isinstance(raw, list) or not raw or not all(isinstance(item, str) for item in raw):
            raise ValueError("local translation provider requires command as a non-empty string array")
        return LocalCommandTranslationProvider(raw)
    raise ValueError("translation provider must be one of: openai, gemini, custom, local")


def _run_translate_events(command: WorkerCommand, dependencies: dict[str, Any]) -> tuple[WorkerEvent, ...]:
    config = command.config
    classified_path = _project_path(command, "classified_path")
    media_path = _project_path(command, "media_path")
    output_path = _project_path(command, "output_path")
    target_language = str(config.get("target_language") or "vi")
    classified = json.loads(classified_path.read_text(encoding="utf-8"))
    media = json.loads(media_path.read_text(encoding="utf-8"))
    if not isinstance(classified, list) or not isinstance(media, dict):
        raise ValueError("translation inputs have invalid JSON shape")
    fps = float(media.get("fps", 0.0))
    if fps <= 0:
        raise ValueError("media fps is required for translation timing")
    segments: list[SubtitleSegment] = []
    for item in coalesce_dialogue_events(classified):
        if not isinstance(item, dict):
            continue
        if str(item.get("text_type")) != "dialogue_subtitle":
            continue
        if str(item.get("review_status")) not in {"auto", "approved"}:
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        start_frame = max(0, int(item.get("start_frame", 0)))
        end_frame = max(start_frame, int(item.get("end_frame", start_frame)))
        start_ms = int(round(start_frame / fps * 1000.0))
        end_ms = int(round((end_frame + 1) / fps * 1000.0))
        segments.append(SubtitleSegment(
            id=str(item.get("event_id") or f"event-{len(segments)+1}"),
            start_ms=start_ms, end_ms=max(start_ms + 1, end_ms),
            source_language="zh", source_text=text, target_language=target_language,
            ocr_confidence=float(item.get("confidence", 0.0)),
            classification_confidence=float(item.get("classification_confidence", 0.0)),
            text_type=TextType.DIALOGUE_SUBTITLE, review_status=ReviewStatus.AUTO,
            anchor=_anchor_from_bbox([int(v) for v in (item.get("anchor_bbox") or item.get("bbox") or [0, 0, 0, 0])]),
        ))
    provider = dependencies.get("translation_provider") or _build_translation_provider(config)
    glossary: dict[str, str] = {}
    glossary_path = config.get("glossary_path")
    if glossary_path:
        raw_glossary = json.loads(Path(str(glossary_path)).read_text(encoding="utf-8"))
        if not isinstance(raw_glossary, dict):
            raise ValueError("glossary must be a JSON object")
        glossary = {str(k): str(v) for k, v in raw_glossary.items()}
    translated = TranslationService(provider).translate(segments, target_language=target_language, glossary=glossary)
    payload = [{
        "id": item.id, "start_ms": item.start_ms, "end_ms": item.end_ms,
        "source_text": item.source_text, "target_text": item.translated_text,
        "natural_translation": item.natural_translation,
        "optimized_translation": item.subtitle_optimized_translation,
        "anchor": list(item.anchor) if item.anchor else None,
    } for item in translated]
    _write_json(output_path, payload)
    return (
        _event(command, WorkerEventType.STARTED, 0.0, "Translation started"),
        _event(command, WorkerEventType.COMPLETED, 1.0, "Translation completed", {"output_path": str(output_path), "count": len(payload)}),
    )


def _run_render_final(command: WorkerCommand, dependencies: dict[str, Any]) -> tuple[WorkerEvent, ...]:
    config = command.config
    clean_video = _project_path(command, "clean_video_path")
    translated_path = _project_path(command, "translated_path")
    output_path = _project_path(command, "output_path")
    srt_path = _project_path(command, "srt_path")
    target_language = str(config.get("target_language") or "vi")
    raw = json.loads(translated_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("translated segments must contain an array")
    segments = [SubtitleSegment(
        id=str(item.get("id") or f"segment-{index+1}"),
        start_ms=int(item.get("start_ms", 0)), end_ms=int(item.get("end_ms", 0)),
        source_language="zh", source_text=str(item.get("source_text") or ""),
        target_language=target_language,
        natural_translation=str(item.get("target_text") or ""),
        subtitle_optimized_translation=str(item.get("target_text") or ""),
        anchor=tuple(int(v) for v in item["anchor"]) if item.get("anchor") else None,
    ) for index, item in enumerate(raw) if isinstance(item, dict)]
    style_config = config.get("style", {})
    if not isinstance(style_config, dict):
        raise ValueError("style must be an object")
    allowed = {name for name in SubtitleStyle.__dataclass_fields__}
    style = SubtitleStyle(**{key: value for key, value in style_config.items() if key in allowed})
    renderer = dependencies.get("renderer") or SubtitleRenderer()
    result = renderer.export(
        clean_video=clean_video, segments=segments, style=style,
        output_path=output_path, srt_path=srt_path,
    )
    return (
        _event(command, WorkerEventType.STARTED, 0.0, "Final render started"),
        _event(command, WorkerEventType.COMPLETED, 1.0, "Final render completed", {"output_path": str(result.output_path), "srt_path": str(result.srt_path)}),
    )

def _fill_bbox(mask: np.ndarray, bbox: tuple[int, int, int, int]) -> None:
    x, y, w, h = bbox
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(mask.shape[1], x + w), min(mask.shape[0], y + h)
    if x1 > x0 and y1 > y0:
        mask[y0:y1, x0:x1] = 255


def _anchor_from_bbox(bbox: list[int]) -> tuple[int, int] | None:
    if len(bbox) != 4:
        return None
    x, y, w, h = bbox
    if w <= 0 or h <= 0:
        return None
    return (int(x + w / 2), int(y + h))


def _glyph_presence_delta(frame: np.ndarray, mask: np.ndarray) -> float:
    """Ratio of high-pass energy inside the mask versus its surround.

    Burned-in glyph edges dominate the masked area's high-pass signal while
    a text-free region shows the same texture energy as its surround. The
    ratio is independent of absolute brightness, so it keeps working on
    bright backgrounds where a plain luminance difference reads as zero.
    """
    hard = mask > 0
    if not np.any(hard):
        return 0.0
    ring = cv2.dilate(mask, np.ones((11, 11), np.uint8)) > 0
    ring &= ~hard
    if not np.any(ring):
        return 0.0
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
    high_pass = gray - cv2.boxFilter(gray, -1, (41, 41))
    ring_energy = float(np.abs(high_pass[ring]).mean())
    return float(np.abs(high_pass[hard]).mean()) / (ring_energy + 1e-6)



def _bright_glyph_mask(
    frame: np.ndarray,
    bbox: tuple[int, int, int, int],
    anchor_bbox: tuple[int, int, int, int] | None = None,
) -> np.ndarray:
    """Capture white subtitle fill that a temporal edge mask can miss."""
    height, width = frame.shape[:2]
    x, y, w, h = bbox
    x0, x1 = 0, width
    y0, y1 = max(0, y), min(height, y + h)
    if anchor_bbox is not None:
        _, anchor_y, _, anchor_h = anchor_bbox
        if anchor_h >= max(12, int(round(h * 0.3))):
            pad_y = max(4, int(round(anchor_h * 0.15)))
            y0 = max(y0, anchor_y - pad_y)
            y1 = min(y1, anchor_y + anchor_h + pad_y)
    result = np.zeros((height, width), np.uint8)
    if x1 <= x0 or y1 <= y0:
        return result

    hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    candidate = ((hsv[:, :, 1] < 60) & (hsv[:, :, 2] > 180)).astype(np.uint8) * 255
    candidate = cv2.morphologyEx(candidate, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(candidate)
    kept = np.zeros_like(candidate)
    max_component = max(24, int(round((y1 - y0) * 0.9)))
    for label in range(1, count):
        _, _, component_w, component_h, area = stats[label]
        if area >= 3 and component_w <= max_component and component_h <= max_component:
            kept[labels == label] = 255
    kept = cv2.dilate(kept, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    result[y0:y1, x0:x1] = kept
    return result


def _has_handle(item: dict[str, Any]) -> bool:
    text = str(item.get("text") or "").casefold()
    return "@" in text or "svip" in text or text.startswith("tg")


def _handle_protection_mask(frame: np.ndarray, item: dict[str, Any]) -> np.ndarray:
    """Protect watermark strokes without reserving a merged subtitle bbox."""
    result = np.zeros(frame.shape[:2], np.uint8)
    raw = item.get("bbox")
    if not isinstance(raw, list) or len(raw) != 4:
        return result
    x, y, w, h = (int(v) for v in raw)
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(frame.shape[1], x + w), min(frame.shape[0], y + h)
    if x1 <= x0 or y1 <= y0:
        return result
    hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    candidate = ((hsv[:, :, 1] < 80) & (hsv[:, :, 2] > 120)).astype(np.uint8) * 255
    if h > 100:
        candidate[: int(round(candidate.shape[0] * 0.35))] = 0
    count, labels, stats, _ = cv2.connectedComponentsWithStats(candidate)
    kept = np.zeros_like(candidate)
    max_height = max(18, min(36, int(round(h * 0.6))))
    for label in range(1, count):
        _, _, component_w, component_h, area = stats[label]
        if 2 <= area and component_h <= max_height and component_w <= 48:
            kept[labels == label] = 255
    text = str(item.get("text") or "")
    first_cjk = next((index for index, char in enumerate(text) if "\u3400" <= char <= "\u9fff"), -1)
    if first_cjk > 0 and _has_handle(item):
        # OCR occasionally joins a small handle with a large subtitle. Keep
        # protection around the handle prefix instead of the merged CJK tail.
        _, xs = np.nonzero(kept)
        if xs.size:
            cutoff = int(xs.min() + first_cjk * max_height * 0.52)
            kept[:, max(0, min(kept.shape[1], cutoff)):] = 0
    kept = cv2.dilate(kept, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    result[y0:y1, x0:x1] = kept
    return result


def _unknown_in_subtitle_band(item: dict[str, Any], frame_height: int) -> bool:
    if str(item.get("text_type") or "unknown") != "unknown" or _has_handle(item):
        return False
    raw = item.get("bbox")
    if not isinstance(raw, list) or len(raw) != 4:
        return False
    _, y, _, h = (int(v) for v in raw)
    center_y = y + h / 2.0
    return 0.64 * frame_height <= center_y <= 0.73 * frame_height and h <= 180


def _is_erase_candidate(item: dict[str, Any], frame_height: int) -> bool:
    text_type = str(item.get("text_type") or "unknown")
    review_status = str(item.get("review_status") or "needs_review")
    if text_type == "dialogue_subtitle" and review_status in {"auto", "approved"}:
        return True
    if not _unknown_in_subtitle_band(item, frame_height):
        return False
    _, _, w, h = (int(v) for v in item["bbox"])
    return w >= 250 and 20 <= h <= 120


def protected_bbox_for_frame(item: dict[str, Any], frame_index: int) -> tuple[int, int, int, int]:
    samples = item.get("samples")
    if isinstance(samples, list) and samples:
        best = min(
            samples,
            key=lambda s: abs(int(s.get("frame_index", 0)) - frame_index),
        )
        raw = best.get("bbox")
        if isinstance(raw, list) and len(raw) == 4:
            sample = tuple(int(v) for v in raw)
            aggregate = item.get("bbox")
            if _has_handle(item) and isinstance(aggregate, list) and len(aggregate) == 4:
                ax, _, aw, ah = (int(v) for v in aggregate)
                if ah > 100:
                    _, sy, _, sh = sample
                    protected_y = sy + int(round(sh * 0.65))
                    return (ax, protected_y, aw, max(1, sy + sh + 8 - protected_y))
            return sample
    raw = item.get("bbox")
    if isinstance(raw, list) and len(raw) == 4:
        return tuple(int(v) for v in raw)
    return (0, 0, 0, 0)


def _build_eraser(dependencies: dict[str, Any], config: dict[str, Any]):
    injected = dependencies.get("eraser")
    if injected is not None:
        return injected
    classical = ClassicalEraser()
    provider_name = str(config.get("provider") or "").strip().lower()
    if not provider_name:
        return classical
    plugin = _build_temporal_provider(config)
    return HybridEraser(classical=classical, plugin=plugin)


def _run_erase_video(command: WorkerCommand, dependencies: dict[str, Any]) -> tuple[WorkerEvent, ...]:
    config = command.config
    video_path = _project_path(command, "video_path")
    classified_path = _project_path(command, "classified_path")
    output_path = _project_path(command, "output_path")
    report_path = _project_path(command, "report_path")
    if not video_path.is_file():
        raise FileNotFoundError(video_path)
    classified = json.loads(classified_path.read_text(encoding="utf-8"))
    if not isinstance(classified, list):
        raise ValueError("classified events must contain an array")
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"cannot decode video: {video_path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 24.0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if width <= 0 or height <= 0:
        capture.release(); raise ValueError("video dimensions are invalid")
    chunk_size = max(8, int(config.get("chunk_size", 96)))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_video = output_path.with_name(f".{output_path.stem}.video.mkv")
    writer = cv2.VideoWriter(str(temp_video), cv2.VideoWriter_fourcc(*"FFV1"), fps, (width, height))
    if not writer.isOpened():
        capture.release(); raise RuntimeError("cannot open lossless clean-video writer")
    eraser = _build_eraser(dependencies, config)
    global_index = 0
    review_frames: list[int] = []
    source_counts: dict[str, int] = {}
    previous_frame: np.ndarray | None = None
    scene_id = 0
    try:
        while True:
            frames = []
            start_index = global_index
            while len(frames) < chunk_size:
                ok, frame = capture.read()
                if not ok:
                    break
                frames.append(frame)
                global_index += 1
            if not frames:
                break
            subtitle_masks = [np.zeros((height, width), np.uint8) for _ in frames]
            protected_masks = [np.zeros((height, width), np.uint8) for _ in frames]
            scene_ids = []
            for local, frame in enumerate(frames):
                absolute = start_index + local
                if _scene_changed(previous_frame, frame, float(config.get("scene_threshold", 32.0))):
                    scene_id += 1
                scene_ids.append(scene_id)
                previous_frame = frame.copy()
            for item in classified:
                if not isinstance(item, dict):
                    continue
                start = int(item.get("start_frame", 0)); end = int(item.get("end_frame", -1))
                bbox_raw = item.get("bbox")
                if not isinstance(bbox_raw, list) or len(bbox_raw) != 4:
                    continue
                bbox = tuple(int(v) for v in bbox_raw)
                anchor_raw = item.get("anchor_bbox")
                anchor_bbox = (
                    tuple(int(v) for v in anchor_raw)
                    if isinstance(anchor_raw, list) and len(anchor_raw) == 4
                    else None
                )
                text_type = str(item.get("text_type") or "unknown")
                review_status = str(item.get("review_status") or "needs_review")
                locals_in_chunk = [
                    local for local in range(len(frames))
                    if start <= start_index + local <= end
                ]
                if not locals_in_chunk:
                    continue
                if _is_erase_candidate(item, height):
                    # The burned-in text is stationary across its event while
                    # the background moves; the per-pixel minimum over the
                    # event's own frames isolates the glyphs from shimmer.
                    x, y, w0, h0 = bbox
                    rois = [
                        frames[local][max(0, y):y + h0, max(0, x):x + w0]
                        for local in locals_in_chunk
                    ]
                    if 2 <= len(rois) and w0 * h0 * len(rois) <= 40_000_000:
                        generated = temporal_stroke_mask(rois)
                        # The per-pixel minimum erodes the anti-aliased glyph
                        # contour (it varies frame to frame); grow the mask to
                        # cover the dark edge halo or a ghost outline survives.
                        generated = cv2.dilate(
                            generated, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
                        )
                        # The scanner can truncate an event's temporal range
                        # (missed samples at onset/decay). Extend while the
                        # glyph template still reads as present.
                        hard = generated > 0
                        ring = cv2.dilate(generated, np.ones((11, 11), np.uint8)) > 0
                        ring &= ~hard
                        extended = list(locals_in_chunk)
                        if np.any(hard) and np.any(ring):
                            for direction in (-1, 1):
                                edge = min(extended) if direction < 0 else max(extended)
                                steps = 0
                                cursor = edge
                                while steps < 12:
                                    cursor += direction
                                    steps += 1
                                    if not 0 <= cursor < len(frames):
                                        break
                                    roi = frames[cursor][max(0, y):y + h0, max(0, x):x + w0]
                                    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY).astype(np.float32)
                                    if gray.shape[:2] != generated.shape[:2]:
                                        break
                                    high_pass = gray - cv2.boxFilter(gray, -1, (41, 41))
                                    ring_energy = float(np.abs(high_pass[ring]).mean())
                                    delta = float(np.abs(high_pass[hard]).mean()) / (ring_energy + 1e-6)
                                    if delta <= 1.6:
                                        break
                                    extended.append(cursor)
                        x0, y0 = max(0, x), max(0, y)
                        extended = sorted(set(extended))
                        for local in extended:
                            full = np.zeros((height, width), np.uint8)
                            full[y0:y0 + generated.shape[0], x0:x0 + generated.shape[1]] = generated
                            bright = _bright_glyph_mask(frames[local], bbox, anchor_bbox)
                            # White subtitle fill is a more precise template
                            # than temporal minima on highly textured scenes.
                            if np.count_nonzero(bright) >= 40:
                                near_bright = cv2.dilate(
                                    bright,
                                    cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (81, 31)),
                                )
                                full = cv2.bitwise_or(
                                    bright,
                                    cv2.bitwise_and(full, near_bright),
                                )
                            subtitle_masks[local] = cv2.bitwise_or(subtitle_masks[local], full)
                    else:
                        for local in locals_in_chunk:
                            generated = generate_stroke_mask(frames[local], bbox)
                            subtitle_masks[local] = cv2.bitwise_or(subtitle_masks[local], generated)
                else:
                    for local in locals_in_chunk:
                        if text_type == "unknown" and not _has_handle(item):
                            continue
                        if _has_handle(item) or text_type == "watermark":
                            protected_masks[local] = cv2.bitwise_or(
                                protected_masks[local],
                                _handle_protection_mask(frames[local], item),
                            )
                        else:
                            _fill_bbox(protected_masks[local], protected_bbox_for_frame(item, start_index + local))
            kwargs = dict(frames=frames, subtitle_masks=subtitle_masks, protected_masks=protected_masks, scene_ids=scene_ids)
            if isinstance(eraser, HybridEraser):
                kwargs.update(fps=fps, fp16=bool(config.get("fp16", False)))
            batch = eraser.process(**kwargs)
            for local, frame in enumerate(batch.frames):
                writer.write(frame)
            for local in batch.review_frames:
                review_frames.append(start_index + int(local))
            for source in batch.reconstruction_sources:
                source_counts[source] = source_counts.get(source, 0) + 1
    finally:
        capture.release(); writer.release()
    # Preserve the original audio stream while keeping the reconstructed video lossless.
    media = dependencies.get("media") or FFmpegMedia()
    try:
        media.mux_original_audio(temp_video, video_path, output_path)
        temp_video.unlink(missing_ok=True)
    except Exception:
        temp_video.replace(output_path)
    _write_json(report_path, {
        "review_frames": sorted(set(review_frames)),
        "reconstruction_sources": source_counts,
        "frame_count": global_index,
        "provider": str(config.get("provider") or "classical"),
    })
    return (
        _event(command, WorkerEventType.STARTED, 0.0, "Subtitle erasing started"),
        _event(command, WorkerEventType.COMPLETED, 1.0, "Subtitle erasing completed", {"output_path": str(output_path), "report_path": str(report_path), "review_count": len(set(review_frames))}),
    )

def _speech_overlap_for_frames(asr_segments: list[dict[str, Any]], *, start_frame: int, end_frame: int, fps: float) -> float:
    if fps <= 0:
        return 0.0
    start_ms = (start_frame / fps) * 1000.0
    end_ms = ((end_frame + 1) / fps) * 1000.0
    duration = max(end_ms - start_ms, 1.0)
    overlap = 0.0
    for seg in asr_segments:
        try:
            left = max(start_ms, float(seg.get("start_ms", 0)))
            right = min(end_ms, float(seg.get("end_ms", 0)))
        except (TypeError, ValueError):
            continue
        overlap += max(0.0, right - left)
    return float(max(0.0, min(1.0, overlap / duration)))


def _run_classify_text_events(command: WorkerCommand, dependencies: dict[str, Any]) -> tuple[WorkerEvent, ...]:
    config = command.config
    media_path = _project_path(command, "media_path")
    cues_path = _project_path(command, "cues_path")
    asr_path = _project_path(command, "asr_path")
    output_path = _project_path(command, "output_path")
    media = json.loads(media_path.read_text(encoding="utf-8"))
    cues = json.loads(cues_path.read_text(encoding="utf-8"))
    if asr_path.is_file():
        asr_segments = json.loads(asr_path.read_text(encoding="utf-8"))
    elif bool(config.get("asr_optional", False)):
        asr_segments = []
    else:
        raise FileNotFoundError(asr_path)
    if not isinstance(media, dict) or not isinstance(cues, list) or not isinstance(asr_segments, list):
        raise ValueError("classification inputs have invalid JSON shape")
    width = int(media.get("width", 0)); height = int(media.get("height", 0))
    fps = float(media.get("fps", 0.0)); total_frames = int(media.get("frame_count", 0))
    if width <= 0 or height <= 0 or fps <= 0 or total_frames <= 0:
        raise ValueError("media metadata is incomplete for classification")
    classifier = dependencies.get("text_classifier") or TextClassifier()
    payload = []
    for cue in cues:
        if not isinstance(cue, dict):
            raise ValueError("cue entry must be an object")
        start = max(0, int(cue.get("start_frame", 0)))
        end = max(start, int(cue.get("end_frame", start)))
        bbox_raw = cue.get("bbox")
        if not isinstance(bbox_raw, list) or len(bbox_raw) != 4:
            raise ValueError("cue bbox must contain x,y,w,h")
        bbox = tuple(int(v) for v in bbox_raw)
        frame_indices = list(range(start, min(end, total_frames - 1) + 1))
        track = TextTrack(id=str(cue.get("event_id") or ""), frame_indices=frame_indices, bboxes=[bbox] * len(frame_indices))
        overlap = _speech_overlap_for_frames(asr_segments, start_frame=start, end_frame=end, fps=fps)
        result = classifier.classify(
            track,
            frame_size=(width, height),
            total_frames=total_frames,
            recognized_text=str(cue.get("text") or ""),
            speech_overlap=overlap,
            scene_count=1,
            ocr_confidence=float(cue.get("confidence", 0.0)),
        )
        item = dict(cue)
        item.update({
            "text_type": result.text_type.value,
            "review_status": result.review_status.value,
            "classification_confidence": result.confidence,
            "classification_margin": result.margin,
            "speech_overlap": overlap,
        })
        payload.append(item)
    _write_json(output_path, payload)
    review_count = sum(1 for item in payload if item["review_status"] == "needs_review")
    return (
        _event(command, WorkerEventType.STARTED, 0.0, "Text classification started"),
        _event(command, WorkerEventType.COMPLETED, 1.0, "Text classification completed", {"output_path": str(output_path), "count": len(payload), "review_count": review_count}),
    )


def _run_recover_missing_subtitles(command: WorkerCommand, dependencies: dict[str, Any]) -> tuple[WorkerEvent, ...]:
    video_path = _project_path(command, "video_path")
    classified_path = _project_path(command, "classified_path")
    output_path = _project_path(command, "output_path")
    raw = json.loads(classified_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("classified events must contain an array")
    engine = dependencies.get("ocr_engine")
    provider = PaddleOCRProvider(engine=engine) if engine is not None else PaddleOCRProvider()

    def recognize(frame, regions, frame_index):
        result = provider.recognize(frame, regions, frame_index=frame_index)
        best = max(result, key=lambda item: item.confidence, default=None)
        return (best.text, float(best.confidence)) if best is not None else ("", 0.0)

    recovered = recover_missing_events(str(video_path), raw, recognize)
    _write_json(output_path, recovered)
    added = sum(1 for item in recovered if bool(item.get("recovered")))
    return (
        _event(command, WorkerEventType.STARTED, 0.0, "Subtitle recovery started"),
        _event(command, WorkerEventType.COMPLETED, 1.0, "Subtitle recovery completed", {
            "output_path": str(output_path), "recovered_count": added,
        }),
    )

def _run_analyze_media(command: WorkerCommand, dependencies: dict[str, Any]) -> tuple[WorkerEvent, ...]:
    config = command.config
    video_path = _project_path(command, "video_path")
    output_path = _project_path(command, "output_path")
    media = dependencies.get("media") or FFmpegMedia()
    meta = media.probe(video_path)
    payload = {
        "width": meta.width, "height": meta.height, "fps": meta.fps,
        "frame_count": meta.frame_count, "duration_ms": meta.duration_ms,
        "codec": meta.codec, "has_audio": meta.has_audio,
    }
    _write_json(output_path, payload)
    return (
        _event(command, WorkerEventType.STARTED, 0.0, "Media analysis started"),
        _event(command, WorkerEventType.COMPLETED, 1.0, "Media analysis completed", {"output_path": str(output_path)}),
    )


def _run_extract_audio(command: WorkerCommand, dependencies: dict[str, Any]) -> tuple[WorkerEvent, ...]:
    config = command.config
    video_path = _project_path(command, "video_path")
    output_path = _project_path(command, "output_path")
    media = dependencies.get("media") or FFmpegMedia()
    media.extract_audio(video_path, output_path)
    return (
        _event(command, WorkerEventType.STARTED, 0.0, "Audio extraction started"),
        _event(command, WorkerEventType.COMPLETED, 1.0, "Audio extraction completed", {"output_path": str(output_path)}),
    )

def _scene_changed(previous: np.ndarray | None, current: np.ndarray, threshold: float = 32.0) -> bool:
    if previous is None:
        return False
    prev = cv2.resize(previous, (64, 36), interpolation=cv2.INTER_AREA)
    cur = cv2.resize(current, (64, 36), interpolation=cv2.INTER_AREA)
    return float(np.mean(np.abs(prev.astype(np.float32) - cur.astype(np.float32)))) >= threshold


def _persist_text_event(event, frames_dir: Path) -> dict[str, Any]:
    representative = select_representative_sample(event)
    image = fuse_event_ink(event) if len(event.samples) >= 3 else representative.frame
    image_path = frames_dir / f"{event.id}.png"
    if not cv2.imwrite(str(image_path), image):
        raise ValueError(f"cannot write event image: {image_path}")
    ocr_bbox = [0, 0, int(image.shape[1]), int(image.shape[0])] if representative.is_roi else list(event.aggregate_bbox)
    sample_boxes = np.array([sample.bbox for sample in event.samples], dtype=np.float64)
    median_box = np.median(sample_boxes, axis=0) if len(sample_boxes) else np.array(event.aggregate_bbox, dtype=np.float64)
    anchor_bbox = [int(round(v)) for v in median_box]
    return {
        "id": event.id,
        "scene_id": event.scene_id,
        "start_frame": event.start_frame,
        "end_frame": event.end_frame,
        "frame_index": representative.frame_index,
        "bbox": list(event.aggregate_bbox),
        "anchor_bbox": anchor_bbox,
        "ocr_bbox": ocr_bbox,
        "image_path": str(image_path),
        "stability_confidence": event.stability_confidence,
        "needs_review": event.needs_review,
        "samples": [
            {"frame_index": sample.frame_index, "bbox": list(sample.bbox)}
            for sample in event.samples
        ],
    }


def _run_detect_text_events(command: WorkerCommand, dependencies: dict[str, Any]) -> tuple[WorkerEvent, ...]:
    config = command.config
    video_path = _project_path(command, "video_path")
    output_path = _project_path(command, "output_path")
    frames_dir = _project_path(command, "frames_dir")
    if not video_path.is_file():
        raise FileNotFoundError(video_path)
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"cannot decode video: {video_path}")
    source_fps = float(capture.get(cv2.CAP_PROP_FPS) or 24.0)
    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    detector = dependencies.get("text_detector") or MorphGradientDetector()
    scanner = TextEventScanner()
    frame_index = -1
    next_sample = 0.0
    scene_id = 0
    previous_sample: np.ndarray | None = None
    frames_dir.mkdir(parents=True, exist_ok=True)
    payload: list[dict[str, Any]] = []
    closed_events: list[Any] = []
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            frame_index += 1
            if frame_index + 1e-6 < next_sample:
                continue
            if _scene_changed(previous_sample, frame, float(config.get("scene_threshold", 32.0))):
                scene_id += 1
            candidates = detector.detect(frame, frame_index)
            closed_events.extend(scanner.update(frame, candidates, frame_index=frame_index, scene_id=scene_id))
            # Keep only a tiny scene signature instead of a second full-resolution frame.
            previous_sample = cv2.resize(frame, (64, 36), interpolation=cv2.INTER_AREA)
            step = source_fps / max(scanner.recommended_scan_fps, 0.5)
            next_sample = frame_index + max(1.0, step)
    finally:
        capture.release()
    closed_events.extend(scanner.finalize())
    for event in merge_fragmented_events(closed_events):
        payload.append(_persist_text_event(event, frames_dir))
    _write_json(output_path, payload)
    return (
        _event(command, WorkerEventType.STARTED, 0.0, "Text event scan started"),
        _event(command, WorkerEventType.PROGRESS, 0.95, "Text events detected", {"count": len(payload), "total_frames": total_frames}),
        _event(command, WorkerEventType.COMPLETED, 1.0, "Text event scan completed", {"output_path": str(output_path), "count": len(payload)}),
    )


def _run_ocr_events(command: WorkerCommand, dependencies: dict[str, Any]) -> tuple[WorkerEvent, ...]:
    config = command.config
    events_path = _project_path(command, "events_path")
    output_path = _project_path(command, "output_path")
    if not events_path.is_file():
        raise FileNotFoundError(events_path)
    raw_events = json.loads(events_path.read_text(encoding="utf-8"))
    if not isinstance(raw_events, list):
        raise ValueError("events file must contain an array")
    engine = dependencies.get("ocr_engine")
    provider = PaddleOCRProvider(engine=engine) if engine is not None else PaddleOCRProvider()
    cues = []
    for item in raw_events:
        if not isinstance(item, dict):
            raise ValueError("event entry must be an object")
        image_path = Path(str(item.get("image_path") or ""))
        frame = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError(f"cannot decode event image: {image_path}")
        bbox_raw = item.get("bbox")
        if not isinstance(bbox_raw, list) or len(bbox_raw) != 4:
            raise ValueError("event bbox must contain x,y,w,h")
        bbox = tuple(int(v) for v in bbox_raw)
        ocr_bbox_raw = item.get("ocr_bbox", bbox_raw)
        if not isinstance(ocr_bbox_raw, list) or len(ocr_bbox_raw) != 4:
            raise ValueError("event ocr_bbox must contain x,y,w,h")
        ocr_bbox = tuple(int(v) for v in ocr_bbox_raw)
        recognized = provider.recognize(frame, [ocr_bbox], frame_index=int(item.get("frame_index", 0)))
        best = max(recognized, key=lambda result: result.confidence, default=None)
        cues.append({
            "event_id": str(item.get("id") or ""),
            "start_frame": int(item.get("start_frame", 0)),
            "end_frame": int(item.get("end_frame", 0)),
            "frame_index": int(item.get("frame_index", 0)),
            "text": best.text if best is not None else "",
            "confidence": float(best.confidence) if best is not None else 0.0,
            "bbox": list(bbox),
            "anchor_bbox": item.get("anchor_bbox") if isinstance(item.get("anchor_bbox"), list) else list(bbox),
            "samples": item.get("samples") if isinstance(item.get("samples"), list) else [],
        })
    _write_json(output_path, cues)
    return (
        _event(command, WorkerEventType.STARTED, 0.0, "Event OCR started"),
        _event(command, WorkerEventType.PROGRESS, 0.95, "Event OCR completed", {"count": len(cues)}),
        _event(command, WorkerEventType.COMPLETED, 1.0, "Event OCR completed", {"output_path": str(output_path), "count": len(cues)}),
    )

def _build_temporal_provider(config: dict[str, Any]):
    provider_name = str(config.get("provider") or "").strip().lower()
    if provider_name == "propainter":
        repo_dir = _require_path(config, "repo_dir")
        return ProPainterProvider(
            repo_dir=repo_dir,
            python_executable=str(config["python_executable"]) if config.get("python_executable") else None,
        )
    if provider_name == "e2fgvi":
        repo_dir = _require_path(config, "repo_dir")
        checkpoint = _require_path(config, "checkpoint")
        return E2FGVIProvider(
            repo_dir=repo_dir,
            checkpoint=checkpoint,
            python_executable=str(config["python_executable"]) if config.get("python_executable") else None,
            model=str(config.get("model") or "e2fgvi_hq"),
        )
    raise ValueError("temporal provider must be one of: propainter, e2fgvi")


def _run_temporal_inpaint(command: WorkerCommand, dependencies: dict[str, Any]) -> tuple[WorkerEvent, ...]:
    config = command.config
    frames_path = _project_path(command, "frames_path")
    masks_path = _project_path(command, "masks_path")
    output_path = _project_path(command, "output_path")
    if not frames_path.is_file():
        raise FileNotFoundError(frames_path)
    if not masks_path.is_file():
        raise FileNotFoundError(masks_path)
    frames = np.load(frames_path, allow_pickle=False)
    masks = np.load(masks_path, allow_pickle=False)
    if frames.ndim != 4 or frames.shape[-1] != 3:
        raise ValueError("frames array must have shape [N,H,W,3]")
    if masks.ndim != 3 or masks.shape != frames.shape[:3]:
        raise ValueError("masks array must have shape [N,H,W] matching frames")
    if frames.dtype != np.uint8:
        raise ValueError("frames array must be uint8")
    provider = dependencies.get("temporal_provider") or _build_temporal_provider(config)
    result = provider.inpaint(
        [frame for frame in frames],
        [mask for mask in masks],
        InpaintingContext(fps=float(config.get("fps", 24.0)), fp16=bool(config.get("fp16", False))),
    )
    if len(result.frames) != len(frames):
        raise ValueError("temporal provider returned unexpected frame count")
    composed = np.stack(
        [compose_inside_mask(frames[i], result.frames[i], masks[i], feather=2) for i in range(len(frames))],
        axis=0,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f".{output_path.name}.tmp.npy")
    np.save(temp_path, composed, allow_pickle=False)
    temp_path.replace(output_path)
    return (
        _event(command, WorkerEventType.STARTED, 0.0, "Temporal inpainting started"),
        _event(command, WorkerEventType.PROGRESS, 0.9, "Temporal inpainting completed", {"provider": result.provider_name}),
        _event(command, WorkerEventType.COMPLETED, 1.0, "Temporal inpainting completed", {"output_path": str(output_path), "provider": result.provider_name}),
    )

def execute_command(command: WorkerCommand, *, dependencies: dict[str, Any] | None = None) -> tuple[WorkerEvent, ...]:
    deps = dict(dependencies or {})
    try:
        if command.stage == "translate_events":
            return _run_translate_events(command, deps)
        if command.stage == "render_final":
            return _run_render_final(command, deps)
        if command.stage == "erase_video":
            return _run_erase_video(command, deps)
        if command.stage == "classify_text_events":
            return _run_classify_text_events(command, deps)
        if command.stage == "recover_missing_subtitles":
            return _run_recover_missing_subtitles(command, deps)
        if command.stage == "analyze_media":
            return _run_analyze_media(command, deps)
        if command.stage == "extract_audio":
            return _run_extract_audio(command, deps)
        if command.stage == "detect_text_events":
            return _run_detect_text_events(command, deps)
        if command.stage == "ocr_events":
            return _run_ocr_events(command, deps)
        if command.stage == "ocr":
            return _run_ocr(command, deps)
        if command.stage == "asr":
            return _run_asr(command, deps)
        if command.stage == "temporal_inpaint":
            return _run_temporal_inpaint(command, deps)
        raise ValueError(f"unsupported worker stage: {command.stage}")
    except Exception as exc:
        return (
            _event(command, WorkerEventType.STARTED, 0.0, f"{command.stage} started"),
            _event(command, WorkerEventType.FAILED, 0.0, str(exc)),
        )


def main() -> int:
    raw = sys.stdin.readline()
    if not raw.strip():
        print(json.dumps({"error": "worker command is required"}), file=sys.stderr, flush=True)
        return 2
    try:
        command = WorkerCommand.from_json(raw)
    except Exception as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 2
    events = execute_command(command)
    for event in events:
        print(event.to_json(), flush=True)
    return 1 if events[-1].type is WorkerEventType.FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
