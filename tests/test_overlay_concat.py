import pytest
from app.core.subtitle_overlay.concat import concat_verified
from app.core.subtitle_overlay.models import RenderProfile
from app.core.subtitle_overlay.sampling import probe_video
from test_overlay_render import source


def test_concat_copy_preserves_duration_and_rejects_mismatch(tmp_path):
    video = source(tmp_path)
    profile = RenderProfile(640, 360, 10, 1, 'copy')
    out = concat_verified((video, video), tmp_path/'joined.mp4', profile)
    assert probe_video(out)['duration_ms'] == 4000
    with pytest.raises(ValueError):
        concat_verified((video, video), tmp_path/'bad.mp4', RenderProfile(800, 360, 10, 1, 'copy'))
    assert not (tmp_path/'bad.mp4').exists()
