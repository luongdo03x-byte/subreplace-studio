from dataclasses import replace
from pathlib import Path
import pytest
from app.application.overlay_batch import OverlayBatchController
from app.application.batch import BatchItem
from app.application.view_model import ProjectStartRequest, StudioViewModel
from app.core.subtitle_overlay.typography import default_style
from test_overlay_service import NoText
from test_overlay_render import source


def test_external_subtitle_batch_waits_for_all_approvals_then_merges(tmp_path):
    import subprocess
    from app.core.subtitle_overlay.sampling import probe_video
    video = source(tmp_path)
    second = tmp_path/'small.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=blue:s=320x240:r=15:d=2',
                    '-c:v','libx264','-threads','1',str(second)],check=True)
    srt = tmp_path/'vi.srt'
    srt.write_text('1\n00:00:00,000 --> 00:00:02,000\nXin chào Việt Nam\n')
    items = tuple(BatchItem(ProjectStartRequest(str(path), str(tmp_path/f'p{i}'), str(i),
                      subtitle_path=str(srt), dub_enabled=False, overlay_prepare_only=True), tmp_path/f'out{i}.mp4')
                  for i, path in enumerate((video,second)))
    controller = OverlayBatchController(StudioViewModel(), tmp_path/'batch.json', detector=NoText())
    controller.prepare(items, merged_output=tmp_path/'merged.mp4', style=replace(default_style(), font_size=28))
    assert len(controller.rows()) == 2
    assert not items[0].output_path.exists()
    with pytest.raises(ValueError):
        controller.export()
    for row in controller.rows():
        controller.service.approve(row['id'], row['revision'], accept_fallback=True)
    result = controller.export()
    assert result.merged_output.is_file()
    assert abs(probe_video(result.merged_output)['duration_ms'] - 4000) < 100
    assert probe_video(items[0].output_path)['height'] == probe_video(items[1].output_path)['height']
    assert controller.rows()[0]['payload']['layout']['y'] != controller.rows()[1]['payload']['layout']['y']
    reopened = OverlayBatchController(StudioViewModel(), tmp_path/'batch.json', detector=NoText())
    assert all(r['state'] == 'completed' for r in reopened.rows())
    assert reopened.manifest['items'][0]['request']['api_key'] == ''


def test_retry_preserves_custom_source_style(tmp_path):
    video = source(tmp_path)
    srt = tmp_path/'vi.srt'
    srt.write_text('1\n00:00:00,000 --> 00:00:02,000\nXin chào\n')
    item = BatchItem(ProjectStartRequest(str(video), str(tmp_path/'p'), 'p', subtitle_path=str(srt),
                                        dub_enabled=False), tmp_path/'out.mp4')
    controller = OverlayBatchController(StudioViewModel(), tmp_path/'batch.json', detector=NoText())
    controller.prepare((item,), style=replace(default_style(), font_size=28))
    source_id = controller.rows()[0]['id']
    controller.service.set_style(source_id, replace(default_style(), font_size=32))
    controller.service.set_y(source_id, 400)
    row = controller.rows()[0]
    controller.prepare()
    retried = controller.rows()[0]
    assert retried['payload']['style']['font_size'] == 32
    assert retried['payload']['layout']['y'] == 400
    assert retried['revision'] == row['revision']
