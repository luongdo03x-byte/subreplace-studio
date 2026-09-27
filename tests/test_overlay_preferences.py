from dataclasses import replace
from app.core.subtitle_overlay.preferences import PlacementPreferences
from app.core.subtitle_overlay.store import OverlayStore
from app.core.subtitle_overlay.models import Cue
from app.core.subtitle_overlay.typography import default_style
from app.application.overlay_service import OverlayService
from test_overlay_render import source


def test_placement_default_survives_restart_and_can_be_disabled(tmp_path):
    path = tmp_path/'placement.json'
    prefs = PlacementPreferences(path)
    assert prefs.load() is None
    prefs.save(926,1280)
    assert PlacementPreferences(path).load() == 926/1280
    prefs.clear()
    assert PlacementPreferences(path).load() is None


def test_saved_y_skips_all_sampling_and_keeps_previews(tmp_path, monkeypatch):
    def forbidden(*args):
        raise AssertionError('Saved Y must not sample frames or run detection')
    monkeypatch.setattr('app.application.overlay_service.sample_frames',forbidden)
    video = source(tmp_path)
    service = OverlayService(OverlayStore(tmp_path/'state.db'), saved_y_ratio=.75)
    style = replace(default_style(),font_size=28)
    service.prepare('a',video,(Cue('1',0,2000,'Xin chào'),),style)
    payload = service.store.load('a')['payload']
    assert payload['layout']['y'] == round(payload['info']['height']*.75)
    assert payload['band']['measured_frames'] == 0
    assert not payload['layout']['fallback']
    service.finalize_batch('batch',('a',))
    row = service.store.load('a')
    assert len(row['payload']['previews']) == 5
    assert row['approved'] is None
    # A new global default must not move a previously prepared source on retry.
    service.saved_y_ratio = .9
    service.prepare('a',video,(Cue('1',0,2000,'Nội dung mới'),),style)
    assert service.store.load('a')['payload']['layout']['y'] == payload['layout']['y']
