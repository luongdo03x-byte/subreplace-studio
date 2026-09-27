"""Concatenation is stream-copy only; incompatible exports must be rendered anew."""
import json
from pathlib import Path
import subprocess
import tempfile
from fractions import Fraction
from app.core.media.ffmpeg import FFmpegMedia
from .sampling import probe_video


def _signature(path):
    proc = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_data', '-of', 'json', str(path)],
                          check=True, capture_output=True, text=True)
    fields = ('codec_type', 'codec_name', 'profile', 'width', 'height', 'pix_fmt',
              'sample_aspect_ratio', 'r_frame_rate', 'time_base', 'sample_rate',
              'channels', 'channel_layout', 'extradata')
    return [{k: stream.get(k) for k in fields} for stream in json.loads(proc.stdout)['streams']
            if stream['codec_type'] in ('video', 'audio')]


def concat_verified(inputs, output, profile, cancel_event=None):
    if not inputs:
        raise ValueError('Không có nguồn để gộp')
    inputs = tuple(Path(p).resolve() for p in inputs)
    expected = None
    total_ms = 0
    for path in inputs:
        info = probe_video(path)
        if ((info['width'], info['height']) != (profile.width, profile.height)
                or Fraction(info['fps_num'], info['fps_den']) != Fraction(profile.fps_num, profile.fps_den)):
            raise ValueError('Nguồn không khớp cấu hình gộp đã duyệt')
        signature = _signature(path)
        if expected is not None and signature != expected:
            raise ValueError('Stream không tương thích; cần render lại đúng profile, không mã hóa lần hai.')
        expected = signature
        total_ms += info['duration_ms']
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='overlay-concat-', dir=output.parent) as temp:
        manifest = Path(temp)/'concat.txt'
        if any('\n' in str(p) or '\r' in str(p) for p in inputs):
            raise ValueError('Unsupported newline in video path')
        manifest.write_text(''.join("file '" + p.as_posix().replace("'", "'\\''") + "'\n" for p in inputs), encoding='utf-8')
        target = Path(temp)/'merged.mp4'
        result = FFmpegMedia._run_cancellable(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0',
            '-i', str(manifest), '-c', 'copy', '-movflags', '+faststart', str(target)], cancel_event=cancel_event)
        if result.returncode:
            raise ValueError(result.stderr[-2500:])
        actual = probe_video(target)['duration_ms']
        tolerance = len(inputs) * (1000 * profile.fps_den/profile.fps_num + 22)
        if abs(actual-total_ms) > tolerance:
            raise ValueError('Thời lượng sau gộp không khớp các nguồn')
        target.replace(output)
    return output
