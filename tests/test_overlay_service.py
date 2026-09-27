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


def test_preview_and_y_style_edits_reuse_sampled_detection(tmp_path):
    class SampleOnly:
        def __init__(self):
            self.calls = 0

        def detect(self, image, index):
            self.calls += 1
            if self.calls > 20:
                raise AssertionError('Detection must not run again after the 20 distinct sample frames')
            return []

    detector = SampleOnly()
    video = source(tmp_path)
    store = OverlayStore(tmp_path/'state.db')
    messages = []
    service = OverlayService(store, detector=detector, on_progress=messages.append)
    style = replace(default_style(), font_size=28)
    service.prepare('a', video, (Cue('1', 0, 2000, 'Xin chào'),), style)
    assert detector.calls == 20
    service.finalize_batch('batch', ('a',))
    row = store.load('a')
    assert len(row['payload']['previews']) == 5
    service.approve('a', row['revision'], accept_fallback=True)
    # Reopen with a detector that refuses further inference: cached band is durable.
    reopened = OverlayService(store, detector=detector, on_progress=messages.append)
    reopened.set_y('a', 400)
    reopened.set_style('a', replace(style, font_size=30))
    row = store.load('a')
    assert row['payload']['layout']['y'] == 400
    assert len(row['payload']['previews']) == 5
    assert row['approved'] is None
    assert not row['payload']['blocking']
    assert detector.calls == 20
    assert any('Dò mẫu 20/300' in message for message in messages)
    assert any('Tạo ảnh xem trước 5/5' in message for message in messages)


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


def test_legacy_collision_block_is_replaced_by_fresh_sample_only_previews(tmp_path):
    video = source(tmp_path)
    service = OverlayService(OverlayStore(tmp_path/'state.db'), detector=NoText())
    service.prepare('a', video, (Cue('1', 0, 2000, 'Xin chào'),), replace(default_style(), font_size=28))
    service.finalize_batch('batch', ('a',))
    payload = service.store.load('a')['payload']
    payload.pop('preview_policy', None)
    payload.update(blocking=['Phát hiện chồng chữ ở 8 khung'], collision_report='old.json', collision_times=[400])
    service.store.save('a', payload)
    service.finalize_batch('batch', ('a',))
    row = service.store.load('a')
    assert not row['payload']['blocking']
    assert not row['payload'].get('collision_times')
    assert not row['payload'].get('collision_report')
    assert len(row['payload']['previews']) == 5
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
