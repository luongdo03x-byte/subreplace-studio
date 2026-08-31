"""Thanh tien trinh phai liet ke dung cac stage that su chay."""
from __future__ import annotations

from app.application.default_workflow import build_core_commands
from app.ui.processing_view import STAGES
from app.ui.project_setup import DUCK_LEVELS


def test_synthesis_stage_appears_between_translation_and_render():
    assert STAGES.index("translate_events") < STAGES.index("synthesize_speech") < STAGES.index("render_final")


def test_recovery_stage_is_listed(tmp_path):
    # recover_missing_subtitles da chay trong pipeline nhung thieu trong STAGES,
    # nen tien trinh cua no khong bao gio hien.
    assert "recover_missing_subtitles" in STAGES


def test_every_core_pipeline_stage_has_a_progress_row(tmp_path):
    from app.models.project import Project

    root = tmp_path / "project"
    root.mkdir()
    source = root / "source.mp4"
    source.write_bytes(b"")
    project = Project(id="p", name="p", root=root, source_path=source, target_language="vi")
    for command in build_core_commands(project):
        assert command.stage in STAGES, command.stage


def test_duck_levels_map_labels_to_sidechain_ratios():
    assert DUCK_LEVELS == (("Nhẹ", 6), ("Vừa", 12), ("Mạnh", 20))


def test_default_duck_level_is_the_middle_one():
    assert DUCK_LEVELS[1][1] == 12
