from dataclasses import replace
import pytest
from app.application.overlay_service import OverlayService
from app.core.subtitle_overlay.store import OverlayStore
from app.core.subtitle_overlay.models import Cue
from app.core.subtitle_overlay.typography import default_style
from test_overlay_render import source


class NoText:
    def detect(self, image, index):
        return []


def test_prepare_review_render_and_edit_revokes_old_revision(tmp_path):
    video = source(tmp_path)
    store = OverlayStore(tmp_path / 'state.db')
    service = OverlayService(store, detector=NoText())
    service.prepare('a', video, (Cue('1', 0, 2000, 'ệ ợ ữ ậ ỗ ằ'),), replace(default_style(), font_size=28))
    service.finalize_batch('batch', ('a',))
    row = store.load('a')
    assert len(row['payload']['previews']) == 5
    with pytest.raises(ValueError):
        service.render('a', row['revision'], tmp_path / 'out.mp4')
    with pytest.raises(ValueError):
        service.approve('a', row['revision'])
    service.approve('a', row['revision'], accept_fallback=True)
    output = service.render('a', row['revision'], tmp_path / 'out.mp4')
    assert output.is_file()
    timestamp = output.stat().st_mtime_ns
    assert service.render('a', row['revision'], output).stat().st_mtime_ns == timestamp
    newer = service.set_y('a', row['payload']['layout']['y'] + 10)
    assert newer > row['revision']
    assert not store.is_approved('a', newer)
    with pytest.raises(ValueError):
        service.render('a', row['revision'], output)


def test_source_change_after_preview_blocks_approval(tmp_path):
    video = source(tmp_path)
    service = OverlayService(OverlayStore(tmp_path/'state.db'), detector=NoText())
    service.prepare('a', video, (Cue('1', 0, 2000, 'Xin chào'),), replace(default_style(), font_size=28))
    service.finalize_batch('batch', ('a',))
    row = service.store.load('a')
    video.write_bytes(b'changed')
    with pytest.raises(ValueError):
        service.approve('a', row['revision'], accept_fallback=True)


def test_style_change_regenerates_preview_and_keeps_manual_y(tmp_path):
    video = source(tmp_path)
    service = OverlayService(OverlayStore(tmp_path/'state.db'), detector=NoText())
    style = replace(default_style(), font_size=28)
    service.prepare('a', video, (Cue('1',0,2000,'Xin chào'),), style)
    service.finalize_batch('batch', ('a',))
    service.set_y('a', 400)
    old = service.store.load('a')
    service.approve('a', old['revision'], accept_fallback=True)
    service.set_style('a', replace(style, font_size=30))
    new = service.store.load('a')
    assert new['payload']['layout']['y'] == 400
    assert new['approved'] is None
    assert len(new['payload']['previews']) == 5
