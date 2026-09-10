"""Prepare → review → export. No render can bypass a current approval."""
from dataclasses import asdict
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import threading
import uuid

from app.core.subtitle_overlay.band import BandResult, DETECTOR_VERSION, detect_band
from app.core.subtitle_overlay.captions import segment_cues
from app.core.subtitle_overlay.layout import batch_profile, lock_layout
from app.core.subtitle_overlay.models import Cue, DisplayCue, LockedLayout, OverlayStyle, RenderProfile
from app.core.subtitle_overlay.render import write_overlay_ass, render_preview, render_video
from app.core.subtitle_overlay.sampling import probe_video, sample_frames
from app.core.subtitle_overlay.typography import FontMetrics

PREVIEW_POLICY = 'sample-only-v1'


def fingerprint(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


class OverlayService:
    def __init__(self, store, *, detector=None, cancel_event=None, on_progress=None):
        self.store = store
        self._detector = detector
        self.cancel_event = cancel_event or threading.Event()
        self.on_progress = on_progress or (lambda message: None)

    @property
    def detector(self):
        if self._detector is None:
            from app.providers.ocr.paddle_detection import PaddleTextDetector
            self._detector = PaddleTextDetector(detection_only=True)
        return self._detector

    def _frames(self, frames):
        for count, frame in enumerate(frames, 1):
            if self.cancel_event.is_set():
                raise ValueError('Đã dừng xử lý phụ đề')
            self.on_progress(f'Dò mẫu {count}/300 — vị trí {frame.timestamp_ms/1000:.1f}s')
            yield frame

    @staticmethod
    def _style(payload):
        return OverlayStyle(**{**payload['style'], 'font_path': Path(payload['style']['font_path'])})

    def prepare(self, source_id, video, cues, style):
        video = Path(video).resolve()
        inputs = {'video': str(video), 'video_hash': fingerprint(video),
                  'cues': [asdict(cue) for cue in cues],
                  'style': {**asdict(style), 'font_path': str(style.font_path.resolve())},
                  'font_hash': fingerprint(style.font_path), 'detector_version': DETECTOR_VERSION}
        try:
            old = self.store.load(source_id)
        except KeyError:
            old = None
        if old and all(old['payload'].get(key) == value for key, value in inputs.items()):
            return old['revision']
        if old and old['state'] == 'rendering':
            raise ValueError('Nguồn đang render')
        metrics = FontMetrics(style)
        if not metrics.has_glyphs(' '.join(cue.text for cue in cues)):
            raise ValueError('Font thiếu ký tự trong phụ đề')
        info = probe_video(video)
        if any(cue.end_ms > info['duration_ms'] + 50 for cue in cues):
            raise ValueError('Phụ đề vượt thời lượng video')
        display, warnings = segment_cues(cues, metrics, info['width'] - 2*(style.margin_x+style.outline+style.shadow))
        if old and old['payload'].get('video_hash') == inputs['video_hash'] and old['payload'].get('detector_version') == DETECTOR_VERSION:
            band = BandResult(**old['payload']['band'])
        else:
            band = detect_band(self._frames(sample_frames(video)), self.detector, (info['width'], info['height']))
        layout = lock_layout(band, (info['width'], info['height']), metrics.line_height)
        return self.store.save(source_id, {**inputs, 'info': info, 'band': asdict(band),
            'layout': asdict(layout), 'line_height': metrics.line_height,
            'display': [asdict(c) for c in display], 'warnings': list(warnings)+list(band.warnings),
            'blocking': ['Chưa tạo ảnh xem trước.'], 'previews': []})

    def finalize_batch(self, batch_id, source_ids, *, merge=True):
        rows = [self.store.load(source_id) for source_id in source_ids]
        first = rows[0]['payload']['info']
        profile = batch_profile(tuple((r['payload']['info']['width'], r['payload']['info']['height'],
                                       LockedLayout(**r['payload']['layout'])) for r in rows),
                                Fraction(first['fps_num'], first['fps_den']), merge)
        self.store.save_batch(batch_id, source_ids, {**asdict(profile), 'merge': merge})
        for row in rows:
            payload = dict(row['payload'])
            local_profile = profile if merge else batch_profile(
                ((payload['info']['width'], payload['info']['height'], LockedLayout(**payload['layout'])),),
                Fraction(payload['info']['fps_num'], payload['info']['fps_den']), False)
            if (payload.get('profile') == asdict(local_profile) and payload.get('checked')
                    and payload.get('preview_policy') == PREVIEW_POLICY
                    and len(payload.get('previews', [])) == 5 and self._artifacts_valid(payload)):
                continue
            payload.update(profile=asdict(local_profile), batch_id=batch_id, checked=False,
                           blocking=['Đang tạo 5 ảnh xem trước.'], previews=[])
            self.store.save(row['id'], payload)  # Revoke old approval before expensive work.
            try:
                payload = self._preview(row['id'], payload)
            except Exception as exc:
                payload['blocking'] = [str(exc)]
                payload['checked'] = False
            self.store.save(row['id'], payload)
            if self.cancel_event.is_set():
                break

    def _preview(self, source_id, payload):
        self._check_inputs(payload)
        video = Path(payload['video'])
        profile = RenderProfile(**payload['profile'])
        layout = LockedLayout(**payload['layout'])
        style = self._style(payload)
        cues = tuple(DisplayCue(**c) for c in payload['display'])
        artifacts = self.store.path.parent / 'overlay-artifacts' / hashlib.sha256(source_id.encode()).hexdigest()[:16] / uuid.uuid4().hex
        artifacts.mkdir(parents=True)
        ass = write_overlay_ass(artifacts/'vi.ass', cues, style, layout, profile)
        # Placement is determined once from the sampled band. Preview and manual
        # edits must never trigger another detector pass over the source.
        payload = dict(payload)
        payload.pop('collision_report', None)
        payload.pop('collision_times', None)
        previews = []
        duration = payload['info']['duration_ms']
        for i in range(5):
            if self.cancel_event.is_set():
                raise ValueError('Đã dừng tạo ảnh xem trước')
            self.on_progress(f'Tạo ảnh xem trước {i+1}/5')
            left, right = duration*i/5, duration*(i+1)/5
            available = [c for c in cues if c.start_ms < right and c.end_ms > left]
            sample_text = not available
            if available:
                chosen = available[len(available)//2]
                timestamp = int((max(left, chosen.start_ms)+min(right, chosen.end_ms))/2)
                preview_ass = ass
            else:
                timestamp = int((left+right)/2)
                preview_ass = write_overlay_ass(artifacts/f'sample-{i}.ass',
                    (DisplayCue('sample', 0, duration, ('ệ ợ ữ ậ ỗ ằ', 'Phụ đề tiếng Việt')),), style, layout, profile)
            image = render_preview(video, timestamp, preview_ass, profile, artifacts/f'{i+1}.png', self.cancel_event)
            previews.append({'path': str(image), 'timestamp_ms': timestamp, 'sample_text': sample_text,
                             'hash': fingerprint(image)})
        return {**payload, 'blocking': [], 'checked': True, 'previews': previews,
                'preview_policy': PREVIEW_POLICY,
                'ass': str(ass), 'ass_hash': fingerprint(ass),
                'render_font': str(ass.parent/'fonts'/style.font_path.name),
                'render_font_hash': fingerprint(style.font_path)}

    @staticmethod
    def _artifacts_valid(payload):
        try:
            return (all(fingerprint(p['path']) == p['hash'] for p in payload['previews'])
                    and fingerprint(payload['ass']) == payload['ass_hash']
                    and fingerprint(payload['render_font']) == payload['render_font_hash'])
        except (OSError, KeyError):
            return False

    @staticmethod
    def _check_inputs(payload):
        if (fingerprint(payload['video']) != payload['video_hash']
                or fingerprint(payload['style']['font_path']) != payload['font_hash']):
            raise ValueError('Video hoặc font đã thay đổi; hãy phân tích và duyệt lại.')
        if payload.get('subtitle_input') and fingerprint(payload['subtitle_input']) != payload['subtitle_hash']:
            raise ValueError('Bản dịch đã thay đổi; hãy chuẩn bị và duyệt lại.')
        if payload.get('dub_audio') and fingerprint(payload['dub_audio']) != payload['dub_hash']:
            raise ValueError('Audio lồng tiếng đã thay đổi; hãy chuẩn bị lại.')

    def set_y(self, source_id, y):
        row = self.store.load(source_id)
        payload = dict(row['payload'])
        layout = lock_layout(BandResult(**payload['band']), (payload['info']['width'], payload['info']['height']),
                             payload['line_height'], manual_y=y)
        payload.update(layout=asdict(layout), manual_y=y, checked=False, previews=[], blocking=['Cần duyệt lại vị trí.'])
        self.store.save(source_id, payload)
        if payload.get('batch_id'):
            batch = self.store.load_batch(payload['batch_id'])
            self.finalize_batch(payload['batch_id'], tuple(batch['source_ids']), merge=batch['profile'].get('merge', True))
        return self.store.load(source_id)['revision']

    def approve(self, source_id, revision, *, accept_fallback=False):
        row = self.store.load(source_id)
        payload = row['payload']
        if row['revision'] != revision:
            raise ValueError('Preview đã thay đổi')
        self._check_inputs(payload)
        if not payload.get('checked') or len(payload.get('previews', [])) != 5 or not self._artifacts_valid(payload):
            raise ValueError('Preview chưa đầy đủ hoặc đã thay đổi')
        if payload['layout']['fallback'] and not accept_fallback:
            raise ValueError('Cần xác nhận rõ vị trí mặc định')
        self.store.approve(source_id, revision)

    def set_style(self, source_id, style):
        old = self.store.load(source_id)['payload']
        self.prepare(source_id, Path(old['video']), tuple(Cue(**c) for c in old['cues']), style)
        payload = self.store.load(source_id)['payload']
        for key in ('subtitle_input', 'subtitle_hash', 'dub_audio', 'dub_hash', 'duck_ratio', 'batch_id'):
            if key in old:
                payload[key] = old[key]
        if 'manual_y' in old:
            payload['manual_y'] = old['manual_y']
            payload['layout'] = asdict(lock_layout(BandResult(**payload['band']),
                (payload['info']['width'], payload['info']['height']), payload['line_height'], old['manual_y']))
        self.store.save(source_id, payload)
        batch = self.store.load_batch(old['batch_id'])
        self.finalize_batch(old['batch_id'], tuple(batch['source_ids']), merge=batch['profile'].get('merge', True))
        return self.store.load(source_id)['revision']

    def render(self, source_id, revision, output, cancel_event=None):
        row = self.store.load(source_id)
        if not self.store.is_approved(source_id, revision):
            raise ValueError('Cần duyệt phiên bản preview hiện tại trước khi xuất')
        payload = row['payload']
        self._check_inputs(payload)
        if not self._artifacts_valid(payload):
            raise ValueError('Preview/ASS/font đã thay đổi')
        output = Path(output)
        marker = output.with_suffix('.overlay.json')
        if row['state'] == 'completed' and output.is_file() and marker.is_file():
            saved = json.loads(marker.read_text(encoding='utf-8'))
            if (saved.get('source_id') == source_id and saved.get('revision') == revision
                    and saved.get('output_hash') == fingerprint(output)):
                return output
        self.store.set_state(source_id, revision, 'rendering')
        try:
            render_video(Path(payload['video']), Path(payload['ass']), RenderProfile(**payload['profile']), output,
                         dub_audio=payload.get('dub_audio'), cancel_event=cancel_event or self.cancel_event,
                         duck_ratio=payload.get('duck_ratio', 12))
            layout = payload['layout']
            _write_json(marker, {'source_id': source_id, 'revision': revision,
                'y_da_khoa': layout['y'], 'chieu_cao_dai_them': layout['extra_height'],
                'che_do': 'mo_rong_khung' if layout['extra_height'] else 'xep_duoi',
                'dung_gia_tri_mac_dinh': layout['fallback'], 'so_khung_mau_do_duoc': layout['measured_frames'],
                'canh_bao': payload['warnings'], 'canvas': payload['profile'], 'output_hash': fingerprint(output)})
            self.store.set_state(source_id, revision, 'completed')
        except Exception:
            self.store.set_state(source_id, revision, 'failed')
            raise
        return output
