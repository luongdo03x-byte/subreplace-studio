import numpy as np
from app.core.detection.protocol import TextCandidate
from app.core.subtitle_overlay.sampling import FrameSample
from app.core.subtitle_overlay.band import detect_band


class Detector:
    def __init__(self, boxes):
        self.boxes = boxes

    def detect(self, image, index):
        # Detector sees bottom half: y coordinates are local to that crop.
        return [TextCandidate(b, (), 1., index) for b in self.boxes(index)]


def frames(n=100):
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    return (FrameSample(i, i * 40, image) for i in range(n))


def test_p95_uses_boxes_in_persistent_band_not_max():
    detector = Detector(lambda i: [(700, (900 if i < 95 else 920) - 540 - 30, 500, 30),
                                    (0, 500, 100, 20)])
    result = detect_band(frames(), detector, (1920, 1080))
    assert result.bottom == 901
    assert result.measured_frames == 100


def test_frequency_counts_frames_not_boxes():
    assert detect_band(frames(), Detector(lambda i: [(700, 330, 500, 30)] * 10 if i < 19 else []),
                       (1920, 1080)).bottom is None
    assert detect_band(frames(), Detector(lambda i: [(700, 330, 500, 30)] if i < 20 else []),
                       (1920, 1080)).bottom == 900


def test_two_lines_are_one_block_and_offcenter_sign_is_filtered():
    result = detect_band(frames(), Detector(lambda i: [(700, 300, 500, 25), (750, 340, 400, 25),
                                                       (0, 440, 100, 20)]), (1920, 1080))
    assert result.bottom == 905
