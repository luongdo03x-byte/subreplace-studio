from pathlib import Path
from app.models.project import Project
from app.application.default_workflow import build_full_commands


def test_preparation_keeps_translation_and_dub_but_never_erases_or_renders(tmp_path):
    project = Project('id', 'p', tmp_path, tmp_path/'source.mp4', 'vi')
    project.settings['overlay_prepare_only'] = True
    commands = build_full_commands(project, translation_config={}, erase_enabled=True, dub_config={'voice': 'a'})
    stages = [c.stage for c in commands]
    assert 'translate_events' in stages
    assert 'synthesize_speech' in stages
    assert 'erase_video' not in stages
    assert 'render_final' not in stages
