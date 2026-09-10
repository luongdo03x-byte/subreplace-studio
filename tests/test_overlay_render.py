from dataclasses import replace
from pathlib import Path
import subprocess
import cv2
import numpy as np
from app.core.subtitle_overlay.models import DisplayCue, LockedLayout, RenderProfile
from app.core.subtitle_overlay.typography import default_style
from app.core.subtitle_overlay.render import write_overlay_ass, render_preview, render_video
from app.core.subtitle_overlay.sampling import probe_video, sample_frames


def source(tmp_path):
    video = tmp_path / 'source.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=black:s=640x360:r=10:d=2',
                    '-c:v', 'libx264', '-threads', '1', str(video)], check=True)
    return video


def test_preview_one_and_two_lines_same_top_and_original_region(tmp_path):
    video = source(tmp_path)
    style = replace(default_style(), font_size=28)
    layout = LockedLayout(370, 110, False, 300)
    profile = RenderProfile(640, 470, 10, 1, 'aac_stereo')
    ass = write_overlay_ass(tmp_path / 'vi.ass',
        (DisplayCue('a', 0, 1000, ('ệ ợ ữ ậ ỗ ằ',)),
         DisplayCue('b', 1000, 2000, ('ệ ợ ữ ậ ỗ ằ', 'Xin chào Việt Nam'))), style, layout, profile)
    first = cv2.imread(str(render_preview(video, 500, ass, profile, tmp_path / 'one.png')))
    second = cv2.imread(str(render_preview(video, 1500, ass, profile, tmp_path / 'two.png')))
    ys = [np.where(np.any(frame > 40, axis=2))[0] for frame in (first, second)]
    assert ys[0].min() == ys[1].min()
    assert ys[1].max() < 469
    assert np.array_equal(first[:360], second[:360])
    assert not np.any(first[:360] > 5)
    out = render_video(video, ass, profile, tmp_path / 'out.mp4')
    info = probe_video(out)
    assert info['height'] == 470 and info['has_audio']
    sampled = list(sample_frames(video))
    assert len(sampled) == 20
    assert len({f.index for f in sampled}) == 20
    assert len(list(sample_frames(video, count=1))) == 1


def test_compositor_preserves_detailed_original_pixels(tmp_path):
    video = tmp_path/'pattern.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=s=640x360:r=10:d=1',
                    '-c:v','libx264','-threads','1',str(video)], check=True)
    baseline = tmp_path/'original.png'
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(video),'-ss','0.5','-frames:v','1',
                    '-threads','1',str(baseline)], check=True)
    layout = LockedLayout(375, 110, False, 300)
    profile = RenderProfile(640,470,10,1,'copy')
    ass = write_overlay_ass(tmp_path/'vi.ass', (DisplayCue('a',0,1000,('ệ ợ ữ ậ ỗ ằ',)),),
                            replace(default_style(),font_size=28), layout, profile)
    rendered = render_preview(video,500,ass,profile,tmp_path/'overlay.png')
    assert np.array_equal(cv2.imread(str(baseline)), cv2.imread(str(rendered))[:360])
