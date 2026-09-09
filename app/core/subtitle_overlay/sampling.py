"""Timestamp-preserving streaming decode; memory is bounded to two frames."""
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
import json
import subprocess

import av
import numpy as np


@dataclass(frozen=True)
class FrameSample:
    index: int
    timestamp_ms: int
    image: np.ndarray


def probe_video(video: Path) -> dict:
    proc = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                           '-of', 'json', str(video)], capture_output=True, text=True, check=True)
    payload = json.loads(proc.stdout)
    stream = next(s for s in payload['streams'] if s['codec_type'] == 'video')
    rotation = int(float(stream.get('tags', {}).get('rotate', 0)))
    for side in stream.get('side_data_list', []):
        rotation = int(side.get('rotation', rotation))
    if rotation % 90:
        raise ValueError('Only right-angle display rotation is supported')
    sar = stream.get('sample_aspect_ratio', '1:1')
    if sar not in ('1:1', 'N/A', '0:1'):
        raise ValueError('Video SAR must be 1:1 for pixel-preserving overlay')
    width, height = int(stream['width']), int(stream['height'])
    if rotation % 180:
        width, height = height, width
    fps = Fraction(stream.get('avg_frame_rate', '0/1'))
    if fps <= 0:
        fps = Fraction(stream.get('r_frame_rate', '25/1'))
    return {'width': width, 'height': height, 'rotation': rotation,
            'fps_num': fps.numerator, 'fps_den': fps.denominator,
            'duration_ms': round(float(stream.get('duration') or payload['format']['duration']) * 1000),
            'has_audio': any(s['codec_type'] == 'audio' for s in payload['streams'])}


def iter_frames(video: Path):
    info = probe_video(video)
    with av.open(str(video)) as container:
        stream = container.streams.video[0]
        origin = float((stream.start_time or 0) * stream.time_base)
        for index, frame in enumerate(container.decode(stream)):
            if frame.pts is None:
                raise ValueError('Frame has no timestamp')
            timestamp = round((float(frame.pts * frame.time_base) - origin) * 1000)
            image = frame.to_ndarray(format='bgr24')
            if info['rotation']:
                image = np.ascontiguousarray(np.rot90(image, info['rotation'] // 90))
            yield FrameSample(index, max(0, timestamp), image)


def sample_frames(video: Path, count: int = 300):
    if count <= 0:
        raise ValueError('Sample count must be positive')
    duration = probe_video(video)['duration_ms']
    targets = np.linspace(0, max(0, duration - 1), count)
    previous = None
    position = 0
    emitted = -1
    for current in iter_frames(video):
        while position < count and targets[position] <= current.timestamp_ms:
            chosen = current
            if previous is not None and abs(previous.timestamp_ms - targets[position]) < abs(current.timestamp_ms - targets[position]):
                chosen = previous
            if chosen.index != emitted:
                yield chosen
                emitted = chosen.index
            position += 1
        previous = current
    if previous is not None and previous.index != emitted:
        yield previous
