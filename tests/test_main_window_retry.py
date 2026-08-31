"""_retry_processing phai chuyen tiep erase_enabled va dub_config y het _start_processing.

Ba lo hong da tung xay ra o day: retry bo qua dub_config (mat long tieng
trong im lang), bo qua erase_enabled (Chinese subtitles quay lai man hinh),
va validate temporal plugin ngay ca khi khong xoa phu de. Test nay chay
qua MainWindow._retry_processing that (khong goi build_full_commands truc
tiep) de dong dung lo hong da bi bo lot boi phien ban test vo nghia truoc do.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from app.application.view_model import ProjectStartRequest, StudioViewModel
from app.core.preflight import CudaStatus, PreflightService
from app.ui.main_window import MainWindow


class _FakeProbeResult:
    has_audio = True
    width = 1920
    height = 1080
    fps = 30.0


class _FakeMedia:
    def probe(self, path):
        return _FakeProbeResult()


class _FakeHandle:
    def __init__(self, job_id: str = "job-1") -> None:
        self.job_id = job_id


class _RecordingWorkflow:
    def __init__(self):
        self.started: list[str] | None = None
        self.retried: list[str] | None = None

    def start(self, project, commands, *, on_progress=None):
        self.started = [command.stage for command in commands]
        return _FakeHandle()

    def retry(self, project, job_id, commands, *, on_progress=None):
        self.retried = [command.stage for command in commands]
        return _FakeHandle(job_id)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


def _build_window(qapp):
    window = MainWindow()
    window.session.workflow = _RecordingWorkflow()
    fake_preflight = PreflightService(
        binary_lookup=lambda name: f"/usr/bin/{name}",
        cuda_probe=lambda: CudaStatus(False, None, 0),
        decode_probe=lambda path: (True, "1920x1080 @ 30.000 fps"),
    )
    window.view_model = StudioViewModel(
        session=window.session,
        preflight=fake_preflight,
        media=_FakeMedia(),
        module_probe=lambda name: True,
        temporal_validator=lambda config: None,
        require_desktop=False,
    )
    return window


def _request(tmp_path, **overrides):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fake")
    base = dict(
        source_path=str(source),
        project_root=str(tmp_path / "project"),
        project_name="p",
        dub_enabled=True,
    )
    base.update(overrides)
    return ProjectStartRequest(**base)


def _run_start_then_retry(qapp, tmp_path, **request_overrides):
    window = _build_window(qapp)
    request = _request(tmp_path, **request_overrides)
    handle, report = window.view_model.start(request)
    assert not report.has_failures
    window._last_request = request
    window._retry_processing()
    workflow = window.session.workflow
    assert workflow.started is not None
    assert workflow.retried is not None
    return workflow


def test_retry_matches_start_with_dubbing_on_and_erase_off(qapp, tmp_path):
    workflow = _run_start_then_retry(qapp, tmp_path, erase_subtitles=False)
    assert workflow.retried == workflow.started
    assert "synthesize_speech" in workflow.retried
    assert "erase_video" not in workflow.retried


def test_retry_matches_start_with_dubbing_on_and_erase_on(qapp, tmp_path):
    workflow = _run_start_then_retry(qapp, tmp_path, erase_subtitles=True)
    assert workflow.retried == workflow.started
    assert "synthesize_speech" in workflow.retried
    assert "erase_video" in workflow.retried
