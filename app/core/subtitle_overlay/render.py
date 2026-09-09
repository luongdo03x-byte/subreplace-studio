"""A single filter graph for preview and final export, always reading original video."""
from pathlib import Path
import re
import shutil
import tempfile

from app.core.media.ffmpeg import FFmpegMedia
from app.core.rendering.ass import _ass_time, _escape_ass
from app.core.rendering.renderer import build_filter_complex
from .sampling import probe_video


def write_overlay_ass(path, cues, style, layout, profile):
    path = Path(path)
    if layout.y < 0 or profile.height <= layout.y:
        raise ValueError('Invalid locked position')
    if any(not 1 <= len(c.lines) <= 2 for c in cues):
        raise ValueError('At most two lines per cue')
    if any(c.end_ms <= c.start_ms for c in cues):
        raise ValueError('Invalid cue timing')
    if any(a.end_ms > b.start_ms for a, b in zip(cues, cues[1:])):
        raise ValueError('Overlapping cues would move ASS text')
    for color in (style.fill, style.outline_color):
        if not re.fullmatch(r'&H[0-9A-Fa-f]{8}', color):
            raise ValueError('Invalid ASS color')
    if any(c in style.font_name for c in ',\n\r'):
        raise ValueError('Invalid font name')
    path.parent.mkdir(parents=True, exist_ok=True)
    fonts = path.parent / 'fonts'
    fonts.mkdir(exist_ok=True)
    shutil.copy2(style.font_path, fonts / style.font_path.name)
    events = []
    for cue in cues:
        text = r'\N'.join(_escape_ass(line) for line in cue.lines)
        events.append(f'Dialogue: 0,{_ass_time(cue.start_ms)},{_ass_time(cue.end_ms)},VI,,0,0,0,,{text}')
    path.write_text('\n'.join([
        '[Script Info]', 'ScriptType: v4.00+', f'PlayResX: {profile.width}', f'PlayResY: {profile.height}',
        'WrapStyle: 2', 'ScaledBorderAndShadow: yes', '', '[V4+ Styles]',
        'Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding',
        f'Style: VI,{style.font_name},{style.font_size},{style.fill},&H000000FF,{style.outline_color},&H80000000,0,0,0,0,100,100,0,0,1,{style.outline},{style.shadow},8,{style.margin_x},{style.margin_x},{layout.y},1',
        '', '[Events]', 'Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text', *events, '',
    ]), encoding='utf-8')
    return path


def _escape(path):
    return str(Path(path).resolve()).replace('\\', '/').replace(':', r'\:').replace("'", r"'\''")


def overlay_filter(ass, profile):
    return (f'pad={profile.width}:{profile.height}:trunc((ow-iw)/4)*2:0:black,'
            f"ass=filename='{_escape(ass)}':fontsdir='{_escape(Path(ass).parent / 'fonts')}'")


def _run(command, cancel_event=None):
    proc = FFmpegMedia._run_cancellable(command, cancel_event=cancel_event)
    if proc.returncode:
        raise ValueError(f'FFmpeg: {proc.stderr[-2500:]}')


def render_preview(video, timestamp_ms, ass, profile, output, cancel_event=None):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Output-side seeking retains original timestamps for libass.
    _run(['ffmpeg', '-v', 'error', '-y', '-filter_threads', '1', '-i', str(video),
          '-vf', overlay_filter(ass, profile), '-ss', f'{timestamp_ms/1000:.3f}',
          '-frames:v', '1', '-threads', '1', '-update', '1', str(output)], cancel_event)
    if not output.is_file() or output.stat().st_size == 0:
        raise ValueError('Preview frame unavailable')
    return output


def render_video(video, ass, profile, output, dub_audio=None, cancel_event=None, duck_ratio=12):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    info = probe_video(video)
    if info['width'] > profile.width or info['height'] > profile.height:
        raise ValueError('Source does not fit approved canvas')
    vf = overlay_filter(ass, profile) + f',fps={profile.fps_num}/{profile.fps_den},setsar=1,format=yuv420p'
    with tempfile.TemporaryDirectory(prefix='overlay-export-', dir=output.parent) as temp:
        target = Path(temp) / 'video.mp4'
        cmd = ['ffmpeg', '-v', 'error', '-y', '-filter_threads', '1', '-filter_complex_threads', '1', '-i', str(video)]
        if dub_audio is not None:
            if not Path(dub_audio).is_file():
                raise ValueError('Missing requested dub audio')
            if not info['has_audio']:
                raise ValueError('Dubbing mixer requires original audio')
            graph = build_filter_complex(ass_path='unused', dubbed=True, duck_ratio=duck_ratio)
            graph = graph.replace('[0:v]ass=unused[v];', f'[0:v]{vf}[v];')
            cmd += ['-i', str(dub_audio), '-filter_complex', graph, '-map', '[v]', '-map', '[aout]',
                    '-c:a', 'aac', '-ar', '48000', '-ac', '2']
        elif profile.audio_mode == 'aac_stereo':
            if not info['has_audio']:
                cmd += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
            cmd += ['-vf', vf, '-map', '0:v:0', '-map', '0:a:0' if info['has_audio'] else '1:a:0',
                    '-af', 'aresample=48000,apad', '-c:a', 'aac', '-ar', '48000', '-ac', '2']
        else:
            cmd += ['-vf', vf, '-map', '0:v:0', '-map', '0:a?', '-c:a', 'copy']
        cmd += ['-c:v', 'libx264', '-crf', '18', '-preset', 'medium', '-threads', '2',
                '-video_track_timescale', '90000', '-t', f"{info['duration_ms']/1000:.3f}",
                '-movflags', '+faststart', str(target)]
        _run(cmd, cancel_event)
        result = probe_video(target)
        if (result['width'], result['height']) != (profile.width, profile.height):
            raise ValueError('Output differs from approved canvas')
        target.replace(output)
    return output
