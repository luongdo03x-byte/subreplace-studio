from __future__ import annotations

from app.models.project import Project
from app.workers.protocol import WorkerCommand


def build_core_commands(project: Project, *, has_audio: bool = True) -> tuple[WorkerCommand, ...]:
    root = project.root.resolve()
    media = root / "cache" / "frames" / "media.json"
    events = root / "cache" / "detection" / "events.json"
    event_frames = root / "cache" / "detection" / "event_frames"
    cues = root / "cache" / "ocr" / "cues.json"
    audio = root / "cache" / "audio" / "source.wav"
    asr = root / "cache" / "asr" / "segments.json"
    classified = root / "cache" / "detection" / "classified.json"
    placeholder_job = "pending"
    commands = [
        WorkerCommand(placeholder_job, "analyze_media", str(root), {
            "video_path": str(project.source_path), "output_path": str(media)
        }),
        WorkerCommand(placeholder_job, "detect_text_events", str(root), {
            "video_path": str(project.source_path), "output_path": str(events), "frames_dir": str(event_frames)
        }),
        WorkerCommand(placeholder_job, "ocr_events", str(root), {
            "events_path": str(events), "output_path": str(cues)
        }),
    ]
    if has_audio:
        commands.extend([
            WorkerCommand(placeholder_job, "extract_audio", str(root), {
                "video_path": str(project.source_path), "output_path": str(audio)
            }),
            WorkerCommand(placeholder_job, "asr", str(root), {
                "audio_path": str(audio), "output_path": str(asr), "language": "zh"
            }),
        ])
    commands.append(
        WorkerCommand(placeholder_job, "classify_text_events", str(root), {
            "media_path": str(media), "cues_path": str(cues), "asr_path": str(asr),
            "output_path": str(classified), "asr_optional": not has_audio
        })
    )
    commands.append(
        WorkerCommand(placeholder_job, "recover_missing_subtitles", str(root), {
            "video_path": str(project.source_path),
            "classified_path": str(classified),
            "output_path": str(classified),
        })
    )
    return tuple(commands)


def build_full_commands(
    project: Project,
    *,
    translation_config: dict[str, object],
    temporal_config: dict[str, object] | None = None,
    has_audio: bool = True,
    erase_enabled: bool = False,
    dub_config: dict[str, object] | None = None,
) -> tuple[WorkerCommand, ...]:
    root = project.root.resolve()
    core = list(build_core_commands(project, has_audio=has_audio))
    overlay_prepare = bool(project.settings.get('overlay_prepare_only'))
    if overlay_prepare:
        erase_enabled = False
    media = root / "cache" / "frames" / "media.json"
    classified = root / "cache" / "detection" / "classified.json"
    audio = root / "cache" / "audio" / "source.wav"
    clean = root / "cache" / "clean" / "clean.mkv"
    erase_report = root / "cache" / "clean" / "erase-report.json"
    translated = root / "cache" / "translation" / f"translated_{project.target_language}.json"
    dub_track = root / "cache" / "dub" / f"dub_{project.target_language}.wav"
    dub_report = root / "cache" / "dub" / "dub-report.json"
    final_video = root / "exports" / f"final_{project.target_language}.mp4"
    render_report = root / "exports" / "render-report.json"
    srt = root / "subtitles" / f"target_{project.target_language}.srt"

    if erase_enabled:
        erase_config: dict[str, object] = {
            "video_path": str(project.source_path),
            "classified_path": str(classified),
            "output_path": str(clean),
            "report_path": str(erase_report),
            "chunk_size": 48,
        }
        if temporal_config:
            erase_config.update(temporal_config)
        core.append(WorkerCommand("pending", "erase_video", str(root), erase_config))

    translate_config: dict[str, object] = {
        "classified_path": str(classified),
        "media_path": str(media),
        "output_path": str(translated),
        "target_language": project.target_language,
        **translation_config,
    }
    core.append(WorkerCommand("pending", "translate_events", str(root), translate_config))

    # Dubbing needs the extracted source audio to read speaker pitch, so a
    # silent source turns it off rather than failing the run.
    dubbing = bool(dub_config) and has_audio
    if dubbing:
        # duck_ratio only feeds render_final's audio mix; synthesize_speech
        # never reads it, so keep it out of that stage's config.
        synth_dub_config = {key: value for key, value in dict(dub_config or {}).items() if key != "duck_ratio"}
        core.append(WorkerCommand("pending", "synthesize_speech", str(root), {
            "translated_path": str(translated),
            "source_audio_path": str(audio),
            "media_path": str(media),
            "output_path": str(dub_track),
            "report_path": str(dub_report),
            **synth_dub_config,
        }))

    render_config: dict[str, object] = {
        # The eraser is optional now, so the render reads whichever video is
        # current: the reconstructed plate, or the untouched source.
        "video_path": str(clean if erase_enabled else project.source_path),
        "translated_path": str(translated),
        "output_path": str(final_video),
        "srt_path": str(srt),
        "report_path": str(render_report),
        "target_language": project.target_language,
        # Keeping the Chinese text means the translation must sit below it.
        "subtitle_placement": "on_anchor" if erase_enabled else "below_anchor",
    }
    if dubbing:
        render_config["dub_audio_path"] = str(dub_track)
        render_config["duck_ratio"] = int(dict(dub_config or {}).get("duck_ratio", 12))
    if not overlay_prepare:
        core.append(WorkerCommand("pending", "render_final", str(root), render_config))
    return tuple(core)
