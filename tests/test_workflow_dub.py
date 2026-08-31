"""Bo xoa chu Trung khoi duong chay mac dinh, chen stage long tieng.

PipelineWorker bo qua stage dua tren ten stage va vi tri trong danh sach,
nen start va retry bat buoc phai sinh ra cung mot day lenh.
"""
from __future__ import annotations

from pathlib import Path

from app.application.default_workflow import build_full_commands
from app.models.project import Project

TRANSLATION = {"translation_provider": "openai"}
DUB = {"voice_female": "vi-VN-HoaiMyNeural", "voice_male": "vi-VN-NamMinhNeural",
       "default_gender": "female", "rate": "+0%", "duck_ratio": 12}


def _project(tmp_path):
    root = tmp_path / "project"
    root.mkdir(parents=True, exist_ok=True)
    source = root / "source.mp4"
    source.write_bytes(b"")
    return Project(id="p1", name="p", root=root, source_path=source, target_language="vi")


def _stages(commands):
    return [command.stage for command in commands]


def _config(commands, stage):
    return next(command.config for command in commands if command.stage == stage)


def test_erase_stage_is_absent_by_default(tmp_path):
    commands = build_full_commands(_project(tmp_path), translation_config=TRANSLATION)
    assert "erase_video" not in _stages(commands)


def test_render_reads_the_source_video_when_erase_is_off(tmp_path):
    project = _project(tmp_path)
    commands = build_full_commands(project, translation_config=TRANSLATION)
    assert _config(commands, "render_final")["video_path"] == str(project.source_path)


def test_render_reads_the_clean_video_when_erase_is_on(tmp_path):
    project = _project(tmp_path)
    commands = build_full_commands(project, translation_config=TRANSLATION, erase_enabled=True)
    assert "erase_video" in _stages(commands)
    assert _config(commands, "render_final")["video_path"].endswith("clean.mkv")


def test_placement_is_derived_from_the_erase_setting(tmp_path):
    project = _project(tmp_path)
    off = build_full_commands(project, translation_config=TRANSLATION)
    on = build_full_commands(project, translation_config=TRANSLATION, erase_enabled=True)
    assert _config(off, "render_final")["subtitle_placement"] == "below_anchor"
    assert _config(on, "render_final")["subtitle_placement"] == "on_anchor"


def test_synthesis_runs_between_translation_and_render(tmp_path):
    commands = build_full_commands(_project(tmp_path), translation_config=TRANSLATION, dub_config=DUB)
    stages = _stages(commands)
    assert stages.index("translate_events") < stages.index("synthesize_speech") < stages.index("render_final")


def test_render_receives_the_dub_track_and_duck_ratio(tmp_path):
    commands = build_full_commands(_project(tmp_path), translation_config=TRANSLATION, dub_config=DUB)
    render = _config(commands, "render_final")
    assert render["dub_audio_path"] == _config(commands, "synthesize_speech")["output_path"]
    assert render["duck_ratio"] == 12


def test_silent_source_skips_dubbing_entirely(tmp_path):
    commands = build_full_commands(
        _project(tmp_path), translation_config=TRANSLATION, dub_config=DUB, has_audio=False
    )
    stages = _stages(commands)
    assert "synthesize_speech" not in stages
    assert "dub_audio_path" not in _config(commands, "render_final")


def test_dubbing_off_leaves_render_without_a_dub_track(tmp_path):
    commands = build_full_commands(_project(tmp_path), translation_config=TRANSLATION)
    assert "dub_audio_path" not in _config(commands, "render_final")


def test_synthesis_config_points_at_existing_cache_artifacts(tmp_path):
    commands = build_full_commands(_project(tmp_path), translation_config=TRANSLATION, dub_config=DUB)
    config = _config(commands, "synthesize_speech")
    assert config["source_audio_path"] == _config(commands, "extract_audio")["output_path"]
    assert config["translated_path"] == _config(commands, "translate_events")["output_path"]
    assert config["media_path"] == _config(commands, "analyze_media")["output_path"]


def test_synthesis_config_excludes_duck_ratio(tmp_path):
    # duck_ratio only feeds render_final's audio mix; synthesize_speech never
    # reads it, so its config should carry only the keys it actually uses.
    commands = build_full_commands(_project(tmp_path), translation_config=TRANSLATION, dub_config=DUB)
    assert "duck_ratio" not in _config(commands, "synthesize_speech")
    assert _config(commands, "render_final")["duck_ratio"] == 12
