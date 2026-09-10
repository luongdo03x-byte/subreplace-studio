import json
import pytest
from app.application.subtitle_document import SubtitleDocumentService
from app.core.subtitle_overlay.store import OverlayStore
from app.models.project import Project


def test_editor_revokes_approval_and_refuses_edits_during_render(tmp_path):
    root = tmp_path/'project'
    root.mkdir()
    project = Project('a','p',root,root/'source.mp4','vi')
    manifest = tmp_path/'batch.json'
    project.settings['overlay_manifest'] = str(manifest)
    store = OverlayStore(manifest.with_suffix('.sqlite3'))
    source_id = str(root.resolve())
    rev = store.save(source_id, {'checked':True, 'previews':[]})
    store.approve(source_id, rev)
    path = root/'cache/translation/translated_vi.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps([{'id':'1','target_text':'cũ'}]))
    editor = SubtitleDocumentService()
    editor.update_translation(project, '1', 'mới')
    assert store.load(source_id)['approved'] is None
    assert not store.load(source_id)['payload']['checked']
    rev = store.save(source_id, {'checked':True})
    store.approve(source_id, rev)
    store.set_state(source_id, rev, 'rendering')
    before = path.read_bytes()
    with pytest.raises(ValueError):
        editor.update_translation(project, '1', 'khác')
    assert path.read_bytes() == before
