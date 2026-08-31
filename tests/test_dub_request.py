"""Retry phai dung dung day lenh ma start da dung.

PipelineWorker doi chieu completed_stages theo ten stage va vi tri, nen
neu retry dung tham so khac start thi checkpoint lech va retry chay sai stage.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.application.session import StudioSession
from app.application.view_model import ProjectStartRequest, StudioViewModel
from app.models.project import Project
from app.providers.tts.edge import VOICE_FEMALE, VOICE_MALE


def _request(**overrides):
    base = dict(source_path="/tmp/a.mp4", project_root="/tmp/p", project_name="p")
    base.update(overrides)
    return ProjectStartRequest(**base)


def test_defaults_dub_on_and_erase_off():
    request = _request()
    assert request.dub_enabled is True
    assert request.erase_subtitles is False
    assert request.dub_voice_female == VOICE_FEMALE
    assert request.dub_voice_male == VOICE_MALE
    assert request.dub_default_gender == "female"
    assert request.duck_ratio == 12


def test_dub_config_carries_voices_and_duck_ratio():
    vm = StudioViewModel(require_desktop=False)
    config = vm._dub_config(_request(duck_ratio=20))
    assert config["voice_female"] == VOICE_FEMALE
    assert config["voice_male"] == VOICE_MALE
    assert config["default_gender"] == "female"
    assert config["rate"] == "+0%"
    assert config["duck_ratio"] == 20


def test_dub_config_is_none_when_dubbing_is_off():
    vm = StudioViewModel(require_desktop=False)
    assert vm._dub_config(_request(dub_enabled=False)) is None


def test_dub_config_rejects_a_blank_voice():
    vm = StudioViewModel(require_desktop=False)
    with pytest.raises(ValueError):
        vm._dub_config(_request(dub_voice_female="  "))


def test_dub_config_rejects_an_unknown_default_gender():
    vm = StudioViewModel(require_desktop=False)
    with pytest.raises(ValueError):
        vm._dub_config(_request(dub_default_gender="other"))


def test_dub_config_accepts_a_well_formed_rate():
    vm = StudioViewModel(require_desktop=False)
    config = vm._dub_config(_request(dub_rate="-15%"))
    assert config["rate"] == "-15%"


def test_dub_config_rejects_a_malformed_rate():
    # A user typing "20" instead of "+20%" would otherwise be passed straight
    # to edge-tts and only fail after retry backoff across every line.
    vm = StudioViewModel(require_desktop=False)
    with pytest.raises(ValueError):
        vm._dub_config(_request(dub_rate="20"))


def test_edge_tts_is_required_only_when_dubbing():
    missing = StudioViewModel(require_desktop=False, module_probe=lambda name: name != "edge_tts")
    with_dub = missing._runtime_checks(_request(), has_audio=True)
    without_dub = missing._runtime_checks(_request(dub_enabled=False), has_audio=True)
    assert any(check.name == "edge_tts" and check.status.value == "failed" for check in with_dub)
    assert not any(check.name == "edge_tts" for check in without_dub)


class _RecordingWorkflow:
    def __init__(self):
        self.started = None
        self.retried = None

    def start(self, project, commands, *, on_progress=None):
        self.started = [command.stage for command in commands]
        return object()

    def retry(self, project, job_id, commands, *, on_progress=None):
        self.retried = [command.stage for command in commands]
        return object()


def test_retry_builds_the_same_stage_sequence_as_start(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    source = root / "source.mp4"
    source.write_bytes(b"")
    project = Project(id="p1", name="p", root=root, source_path=source, target_language="vi")
    workflow = _RecordingWorkflow()
    session = StudioSession(workflow=workflow)
    dub_config = {"voice_female": VOICE_FEMALE, "voice_male": VOICE_MALE,
                  "default_gender": "female", "rate": "+0%", "duck_ratio": 12}

    session.start_full(project, translation_config={"translation_provider": "openai"},
                       erase_enabled=False, dub_config=dub_config)
    session.retry_full(project, "job-1", translation_config={"translation_provider": "openai"},
                       erase_enabled=False, dub_config=dub_config)

    assert workflow.started == workflow.retried
    assert "synthesize_speech" in workflow.started
    assert "erase_video" not in workflow.started
