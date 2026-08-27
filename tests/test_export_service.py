from types import SimpleNamespace

from app.application.export_service import ExportService


def _project(tmp_path):
    root = tmp_path / "project"
    (root / "exports").mkdir(parents=True)
    (root / "subtitles").mkdir()
    (root / "exports" / "final_vi.mp4").write_bytes(b"video")
    (root / "subtitles" / "target_vi.srt").write_text("subtitle", encoding="utf-8")
    return SimpleNamespace(root=root, name="sample", target_language="vi")


def test_export_omits_sidecar_subtitle_by_default(tmp_path):
    result = ExportService().export(_project(tmp_path), tmp_path / "output")
    assert [path.name for path in result.files] == ["sample-vi.mp4"]
    assert not (tmp_path / "output" / "sample-vi.srt").exists()


def test_export_can_include_sidecar_subtitle_explicitly(tmp_path):
    result = ExportService().export(
        _project(tmp_path), tmp_path / "output", include_subtitle=True
    )
    assert [path.name for path in result.files] == ["sample-vi.mp4", "sample-vi.srt"]
