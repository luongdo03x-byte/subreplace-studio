from fractions import Fraction
from math import ceil
from .models import LockedLayout, RenderProfile


def lock_layout(band, frame_size, line_height, manual_y=None):
    width, height = frame_size
    if width <= 0 or height <= 0 or line_height <= 0 or (manual_y is not None and manual_y < 0):
        raise ValueError('Invalid layout dimensions')
    fallback = band.bottom is None
    y = ceil(height * (.90 if width >= height else .88)) if fallback else ceil(band.bottom + .008 * height)
    if manual_y is not None:
        if isinstance(manual_y, bool) or int(manual_y) != manual_y:
            raise ValueError('Y must be an integer')
        y = int(manual_y)
    extra = max(0, ceil(y + 2 * line_height + ceil(.02 * height) - height))
    return LockedLayout(y, extra, fallback, band.measured_frames, band.warnings)


def batch_profile(sources, fps: Fraction, merge: bool):
    if not sources or fps <= 0:
        raise ValueError('Missing sources or invalid frame rate')
    width = max(w for w, _, _ in sources)
    height = max(h + layout.extra_height for _, h, layout in sources)
    return RenderProfile(width + width % 2, height + height % 2,
                         fps.numerator, fps.denominator, 'aac_stereo' if merge else 'copy')
