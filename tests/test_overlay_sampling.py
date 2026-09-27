import subprocess
import cv2
import numpy as np
from app.core.subtitle_overlay.sampling import iter_frames, probe_video


def test_detector_orientation_matches_ffmpeg_display_rotation(tmp_path):
    source = tmp_path/'raw.mp4'
    rotated = tmp_path/'rotated.mp4'
    baseline = tmp_path/'baseline.png'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=s=160x96:r=1:d=1',
                    '-c:v','libx264','-threads','1',str(source)],check=True)
    subprocess.run(['ffmpeg','-v','error','-y','-display_rotation:v:0','90','-i',str(source),'-c','copy',str(rotated)],check=True)
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(rotated),'-frames:v','1','-threads','1',str(baseline)],check=True)
    frame = next(iter_frames(rotated)).image
    info = probe_video(rotated)
    assert (info['width'],info['height']) == (96,160)
    expected = cv2.imread(str(baseline))
    assert frame.shape == expected.shape
    assert np.mean(np.abs(frame.astype(float)-expected.astype(float))) < 3
