from __future__ import annotations

import shutil
import subprocess
import threading
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.application.batch import BatchController, BatchItem
from app.application.view_model import ProjectStartRequest
from app.core.jobs.models import JobStatus
from app.core.media.ffmpeg import FFmpegMedia, MediaError
from app.ui.project_setup import _natural_video_key


class _Worker:
    def __init__(self, log, name):
        self.log = log
        self.name = name

    def join(self):
        self.log.append(f"join:{self.name}")


class _Store:
    def __init__(self, status, error=None):
        self.record = SimpleNamespace(status=status, error=error)

    def load(self, _job_id):
        return self.record


class _ViewModel:
    def __init__(self, tmp_path, statuses):
        self.tmp_path = tmp_path
        self.statuses = list(statuses)
        self.session = SimpleNamespace(current_project=None)
        self.log = []
        self.before_return = None

    def start(self, request, *, on_progress=None):
        name = Path(request.source_path).stem
        self.log.append(f"start:{name}")
        root = Path(request.project_root)
        final = root / "exports" / "final_vi.mp4"
        final.parent.mkdir(parents=True)
        final.write_bytes(name.encode("utf-8"))
        self.session.current_project = SimpleNamespace(root=root, target_language="vi")
        status = self.statuses.pop(0)
        handle = SimpleNamespace(
            job_id=name,
            worker=_Worker(self.log, name),
            job_store=_Store(status, "forced failure" if status == JobStatus.FAILED else None),
            cancel=lambda: self.log.append(f"cancel:{name}"),
        )
        if self.before_return is not None:
            self.before_return()
        return handle, SimpleNamespace()


class _Media:
    def __init__(self):
        self.inputs = None

    def concat(self, inputs, output, *, cancel_event=None):
        self.inputs = list(inputs)
        Path(output).write_bytes(b"merged")
        return Path(output)


def _item(tmp_path, index):
    source = tmp_path / f"source-{index}.mp4"
    source.write_bytes(b"source")
    request = ProjectStartRequest(
        source_path=str(source),
        project_root=str(tmp_path / f"project-{index}"),
        project_name=f"project-{index}",
    )
    return BatchItem(request, tmp_path / "output" / f"translated-{index}.mp4")


def test_batch_waits_for_each_video_and_preserves_order(tmp_path):
    view_model = _ViewModel(tmp_path, [JobStatus.COMPLETED] * 3)
    result = BatchController(view_model).run([_item(tmp_path, i) for i in range(3)])
    assert view_model.log == [
        "start:source-0", "join:source-0",
        "start:source-1", "join:source-1",
        "start:source-2", "join:source-2",
    ]
    assert [item.output_path.name for item in result.successful] == [
        "translated-0.mp4", "translated-1.mp4", "translated-2.mp4",
    ]


def test_numeric_video_names_sort_naturally():
    paths = ["/videos/10.mp4", "/videos/2.mp4", "/videos/1.mp4"]
    assert sorted(paths, key=_natural_video_key) == [
        "/videos/1.mp4", "/videos/2.mp4", "/videos/10.mp4",
    ]


def test_failed_video_is_skipped_when_merging(tmp_path):
    view_model = _ViewModel(tmp_path, [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.COMPLETED])
    media = _Media()
    merged = tmp_path / "output" / "merged.mp4"
    merged.parent.mkdir()
    result = BatchController(view_model, media=media).run(
        [_item(tmp_path, i) for i in range(3)], merged_output=merged
    )
    assert len(result.successful) == 2
    assert media.inputs == [
        tmp_path / "output" / "translated-0.mp4",
        tmp_path / "output" / "translated-2.mp4",
    ]
    assert result.merged_output == merged


def test_batch_cleanup_removes_project_cache_after_publish(tmp_path):
    view_model = _ViewModel(tmp_path, [JobStatus.COMPLETED])
    original = _item(tmp_path, 0)
    item = BatchItem(original.request, original.output_path, cleanup_project=True)
    result = BatchController(view_model).run([item])
    assert len(result.successful) == 1
    assert result.successful[0].output_path.is_file()
    assert not Path(original.request.project_root).exists()


def test_retry_reuses_successful_outputs_and_only_runs_failed_video(tmp_path):
    items = [replace(_item(tmp_path, i), cleanup_project=True) for i in range(3)]
    first_view_model = _ViewModel(tmp_path, [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.COMPLETED])
    first = BatchController(first_view_model).run(items)
    completed = {item.source_path.resolve() for item in first.successful}
    retry_items = [
        replace(item, reuse_output=Path(item.request.source_path).resolve() in completed)
        for item in items
    ]

    retry_view_model = _ViewModel(tmp_path, [JobStatus.COMPLETED])
    retried = BatchController(retry_view_model).run(retry_items)

    assert retry_view_model.log == ["start:source-1", "join:source-1"]
    assert len(retried.successful) == 3
    assert [item.output_path for item in retried.successful] == [item.output_path for item in items]


def test_cancel_before_run_does_not_start_first_video(tmp_path):
    view_model = _ViewModel(tmp_path, [JobStatus.COMPLETED])
    controller = BatchController(view_model)
    controller.cancel()
    result = controller.run([_item(tmp_path, 0)])
    assert view_model.log == []
    assert result.cancelled
    assert result.total == 1


def test_cancel_during_handle_handoff_cancels_active_job(tmp_path):
    view_model = _ViewModel(tmp_path, [JobStatus.COMPLETED])
    controller = BatchController(view_model)
    view_model.before_return = controller.cancel
    result = controller.run([_item(tmp_path, 0)])
    assert view_model.log == ["start:source-0", "cancel:source-0", "join:source-0"]
    assert result.cancelled


def test_media_command_does_not_start_after_cancellation():
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(MediaError, match="cancelled"):
        FFmpegMedia._run_cancellable(["command-that-must-not-run"], cancel_event=cancelled)


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg unavailable")
def test_ffmpeg_concat_normalizes_mixed_clips_and_adds_silent_audio(tmp_path):
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    output = tmp_path / "merged.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=red:s=160x120:r=10:d=0.8",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=0.2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(first),
    ], check=True)
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=blue:s=120x160:r=12:d=0.4",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(second),
    ], check=True)
    metadata = FFmpegMedia().probe(FFmpegMedia().concat([first, second], output))
    assert (metadata.width, metadata.height) == (160, 120)
    assert metadata.has_audio
    assert metadata.duration_ms >= 1100
