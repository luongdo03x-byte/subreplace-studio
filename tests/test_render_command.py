"""Filtergraph tron audio, kiem bang so chuoi chu khong chay ffmpeg.

sidechaincompress la MOT filter duy nhat bat ke bao nhieu cau thoai, thay vi
mot filtergraph khong lo voi vai tram bieu thuc enable='between(t,...)'.
"""
from __future__ import annotations

import pytest

from app.core.rendering.renderer import build_filter_complex


def test_without_dubbing_only_the_subtitle_filter_is_built():
    graph = build_filter_complex(ass_path="/tmp/t.ass", dubbed=False, duck_ratio=12)
    assert graph == ""


def test_dubbed_graph_burns_subtitles_and_ducks_the_original():
    graph = build_filter_complex(ass_path="/tmp/t.ass", dubbed=True, duck_ratio=12)
    assert "[0:v]ass=/tmp/t.ass[v]" in graph
    assert "sidechaincompress=" in graph
    assert "ratio=12" in graph
    assert "amix=inputs=2:duration=first:normalize=0[aout]" in graph


def test_duck_ratio_reaches_the_filter():
    for ratio in (6, 12, 20):
        graph = build_filter_complex(ass_path="/tmp/t.ass", dubbed=True, duck_ratio=ratio)
        assert f"ratio={ratio}" in graph


def test_graph_uses_a_single_sidechain_filter_regardless_of_cue_count():
    graph = build_filter_complex(ass_path="/tmp/t.ass", dubbed=True, duck_ratio=12)
    assert graph.count("sidechaincompress") == 1
    assert "enable=" not in graph


def test_attack_and_release_match_the_narration_feel():
    graph = build_filter_complex(ass_path="/tmp/t.ass", dubbed=True, duck_ratio=12)
    assert "attack=20" in graph
    assert "release=400" in graph


@pytest.mark.parametrize("ratio", [0, -1])
def test_invalid_duck_ratio_is_rejected(ratio):
    with pytest.raises(ValueError):
        build_filter_complex(ass_path="/tmp/t.ass", dubbed=True, duck_ratio=ratio)


def test_render_stage_writes_a_placement_report(tmp_path):
    """Canh bao ve vi tri phu de sinh ra o render_final, sau synthesize_speech,
    nen chung khong the ghi nguoc vao dub-report.json."""
    import json

    from app.core.rendering.renderer import RenderResult
    from app.workers.protocol import WorkerCommand, WorkerEventType
    from app.workers.runner import execute_command

    root = tmp_path / "project"
    (root / "cache" / "translation").mkdir(parents=True)
    (root / "cache" / "translation" / "t.json").write_text(json.dumps([
        {"id": "a", "start_ms": 0, "end_ms": 1000, "target_text": "Chao", "anchor": [360, 800]}
    ]), encoding="utf-8")
    source = root / "source.mp4"
    source.write_bytes(b"")

    class _FakeRenderer:
        def export(self, **kwargs):
            return RenderResult(
                output_path=kwargs["output_path"], srt_path=kwargs["srt_path"],
                placement_report={"placement": "below_anchor", "anchor": [360, 800],
                                  "frame_size": [720, 1280], "clamped": True, "min_font_size": 33},
            )

    command = WorkerCommand("job-1", "render_final", str(root), {
        "video_path": str(source),
        "translated_path": str(root / "cache" / "translation" / "t.json"),
        "output_path": str(root / "exports" / "final_vi.mp4"),
        "srt_path": str(root / "subtitles" / "t.srt"),
        "report_path": str(root / "exports" / "render-report.json"),
        "subtitle_placement": "below_anchor",
    })
    events = execute_command(command, dependencies={"renderer": _FakeRenderer()})
    assert events[-1].type is WorkerEventType.COMPLETED, events[-1].message
    report = json.loads((root / "exports" / "render-report.json").read_text(encoding="utf-8"))
    assert report["placement"] == "below_anchor"
    assert report["clamped"] is True
    assert events[-1].data["clamped"] is True


def test_empty_dub_track_falls_back_to_the_plain_render(tmp_path):
    """An interrupted synthesis write must not break the render."""
    from app.core.rendering.renderer import SubtitleRenderer

    empty = tmp_path / "dub.wav"
    empty.write_bytes(b"")
    assert empty.is_file() and empty.stat().st_size == 0

    renderer = SubtitleRenderer()
    # The gate must reject a zero-byte file the same way it rejects a missing one.
    assert renderer._dub_is_usable(empty) is False
    assert renderer._dub_is_usable(tmp_path / "missing.wav") is False

    real = tmp_path / "real.wav"
    real.write_bytes(b"\x00" * 64)
    assert renderer._dub_is_usable(real) is True
