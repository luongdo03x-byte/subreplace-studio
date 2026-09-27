import numpy as np
from app.core.detection.protocol import TextCandidate
from app.core.subtitle_overlay.sampling import FrameSample
from app.core.subtitle_overlay.models import DisplayCue, LockedLayout
from app.core.subtitle_overlay.collision import check_collisions


def test_rare_collision_blocks_without_moving_y():
    class Detector:
        def detect(self, image, index):
            return [TextCandidate((100, 100, 100, 20), (), 1., index)] if index == 300 else []
    image = np.zeros((200, 400, 3), dtype=np.uint8)
    frames = (FrameSample(i, i*40, image) for i in range(301))
    layout = LockedLayout(110, 0, False, 300)
    report = check_collisions(frames, Detector(), (DisplayCue('a', 0, 13000, ('Xin chào',)),), layout, 40, 400)
    assert report.complete
    assert report.checked_frames == 301
    assert report.collisions[0].timestamp_ms == 12000
    assert layout.y == 110
