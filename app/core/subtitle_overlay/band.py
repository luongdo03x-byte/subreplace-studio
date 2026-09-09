from dataclasses import dataclass
import math
import numpy as np

DETECTOR_VERSION = 'overlay-band-v1'


@dataclass(frozen=True)
class BandResult:
    bottom: float | None
    measured_frames: int
    decoded_frames: int
    warnings: tuple[str, ...] = ()


def group_boxes(boxes, width):
    """Union same-line fragments and vertically adjacent bilingual lines."""
    blocks = list(dict.fromkeys(tuple(b) for b in boxes))
    changed = True
    while changed:
        changed = False
        for i, (x, y, w, h) in enumerate(blocks):
            for j in range(i + 1, len(blocks)):
                xx, yy, ww, hh = blocks[j]
                vo = max(0, min(y+h, yy+hh) - max(y, yy))
                ho = max(0, min(x+w, xx+ww) - max(x, xx))
                hg = max(0, max(x, xx) - min(x+w, xx+ww))
                vg = max(0, max(y, yy) - min(y+h, yy+hh))
                if ((vo >= .5 * min(h, hh) and hg <= .04 * width)
                        or (ho >= .5 * min(w, ww) and vg <= 1.5 * min(h, hh))):
                    left, top = min(x, xx), min(y, yy)
                    blocks[i] = (left, top, max(x+w, xx+ww)-left, max(y+h, yy+hh)-top)
                    blocks.pop(j)
                    changed = True
                    break
            if changed:
                break
    return blocks


def detect_band(samples, detector, frame_size):
    width, height = frame_size
    observations = []
    decoded = 0
    for sample in samples:
        decoded += 1
        offset = height // 2
        boxes = [(x, y+offset, w, h) for x, y, w, h in
                 (candidate.bbox for candidate in detector.detect(sample.image[offset:], sample.index))]
        for x, y, w, h in group_boxes(boxes, width):
            if y >= .6 * height and abs(x + w/2 - width/2) < .15 * width:
                observations.append((y+h, sample.index))
    clusters = []
    for bottom, index in sorted(observations):
        if not clusters or bottom - clusters[-1][0][0] > .04 * height:
            clusters.append([])
        clusters[-1].append((bottom, index))
    valid = [pair for cluster in clusters if len({i for _, i in cluster}) >= math.ceil(.2 * decoded)
             for pair in cluster]
    warnings = ('Số khung mẫu thực tế dưới 300.',) if decoded < 300 else ()
    if not valid:
        return BandResult(None, 0, decoded, warnings + ('Không dò được dải phụ đề; dùng vị trí mặc định.',))
    return BandResult(float(np.percentile([b for b, _ in valid], 95, method='linear')),
                      len({i for _, i in valid}), decoded, warnings)
