"""Persistent batch controller, shared by desktop and headless review tools."""
from dataclasses import asdict, replace
import json
from pathlib import Path
import threading

from app.application.batch import BatchItem, BatchItemResult, BatchResult
from app.application.default_workflow import build_full_commands
from app.application.overlay_service import OverlayService, _write_json, fingerprint
from app.application.view_model import ProjectStartRequest
from app.core.credentials import CredentialStore
from app.core.subtitle_overlay.captions import read_cues
from app.core.subtitle_overlay.concat import concat_verified
from app.core.subtitle_overlay.models import Cue, OverlayStyle, RenderProfile
from app.core.subtitle_overlay.store import OverlayStore
from app.core.subtitle_overlay.typography import default_style


class OverlayBatchController:
    def __init__(self, view_model, manifest_path, *, detector=None, on_progress=None):
        self.view_model = view_model
        self.path = Path(manifest_path).resolve()
        self.cancel_event = threading.Event()
        self.service = OverlayService(OverlayStore(self.path.with_suffix('.sqlite3')), detector=detector,
                                      cancel_event=self.cancel_event, on_progress=on_progress)
        self.manifest = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
        for item in self.manifest.get('items', []):
            self.service.store.recover_interrupted(item['id'])

    def cancel(self):
        self.cancel_event.set()
        self.view_model.session.cancel()

    def _save(self):
        _write_json(self.path, self.manifest)

    def rows(self):
        rows = []
        for item in self.manifest.get('items', []):
            try:
                row = self.service.store.load(item['id'])
            except KeyError:
                row = {'id': item['id'], 'revision': 0, 'approved': None, 'state': 'failed',
                       'payload': {'blocking': [item.get('error') or 'Chưa chuẩn bị'], 'previews': []}}
            row['name'] = Path(item['request']['source_path']).name
            if item.get('error'):
                row = {**row, 'state': 'failed', 'payload': {**row['payload'], 'blocking': [item['error']]}}
            rows.append(row)
        return rows

    def _translated(self, request, on_progress):
        source = Path(request.source_path).resolve()
        if request.subtitle_path:
            if request.dub_enabled:
                raise ValueError('Nhập phụ đề có sẵn: tắt lồng tiếng cho phase 1.')
            return read_cues(Path(request.subtitle_path)), None, Path(request.subtitle_path)
        root = Path(request.project_root)
        translated = root/'cache'/'translation'/f'translated_{request.target_language}.json'
        if (root/'project.json').is_file():
            project = self.view_model.session.open_project(root)
            original_hash = project.settings.get('overlay_source_hash')
            if original_hash and original_hash != fingerprint(source):
                raise ValueError('Nguồn đã thay đổi; tạo lô mới để dịch lại đúng nội dung.')
            if not project.settings.get('overlay_prepare_only'):
                raise ValueError('Project không thuộc luồng phụ đề cố định; hãy tạo project mới.')
            commands = build_full_commands(project, translation_config=self.view_model._translation_config(request),
                has_audio=self.view_model.media.probe(source).has_audio,
                dub_config=self.view_model._dub_config(request))
            commands = tuple(c for c in commands if c.stage not in project.completed_stages)
            handle = self.view_model.session.workflow.start(project, commands, on_progress=on_progress) if commands else None
            self.view_model.session.current_handle = handle
        else:
            handle, _ = self.view_model.start(replace(request, overlay_prepare_only=True, erase_subtitles=False), on_progress=on_progress)
            project = self.view_model.session.current_project
            project.settings['overlay_source_hash'] = fingerprint(source)
            self.view_model.session.project_service.save(project)
        if handle is not None:
            if self.cancel_event.is_set():
                handle.cancel()
            handle.worker.join()
            record = handle.job_store.load(handle.job_id)
            if record.status.value != 'completed':
                raise ValueError(record.error or 'Chuẩn bị bản dịch chưa hoàn tất')
        data = json.loads(translated.read_text(encoding='utf-8'))
        cues = tuple(Cue(str(row['id']), int(row['start_ms']), int(row['end_ms']), str(row['target_text'])) for row in data)
        dub = root/'cache'/'dub'/f'dub_{request.target_language}.wav'
        return cues, dub if request.dub_enabled and dub.exists() else None, translated

    def prepare(self, items=None, *, merged_output=None, style=None, on_progress=None, on_item=None):
        self.cancel_event.clear()
        preserve_style = items is None and style is None
        style = style or (OverlayStyle(**{**self.manifest['style'], 'font_path': Path(self.manifest['style']['font_path'])})
                          if self.manifest.get('style') else default_style())
        if items is not None:
            self.manifest = {'items': [
                {'id': str(Path(item.request.project_root).resolve()),
                 'request': {**asdict(item.request), 'api_key': ''}, 'output': str(item.output_path.resolve()), 'error': ''}
                for item in items], 'merged_output': str(merged_output) if merged_output else None,
                'style': {**asdict(style), 'font_path': str(style.font_path)}, 'version': 1}
            requests = [item.request for item in items]
        else:
            requests = [ProjectStartRequest(**entry['request']) for entry in self.manifest['items']]
            requests = [replace(r, api_key=CredentialStore().load(r.translation_provider)) for r in requests]
        self._save()
        ready = []
        for index, (entry, request) in enumerate(zip(self.manifest['items'], requests), 1):
            if self.cancel_event.is_set():
                break
            try:
                entry['error'] = ''
                if on_item:
                    on_item(index, len(requests), Path(request.source_path), 'preparing', '')
                callback = (lambda event, i=index: on_progress(i, len(requests), event)) if on_progress else None
                cues, dub, subtitle_input = self._translated(request, callback)
                source_style = style
                if preserve_style:
                    try:
                        existing = self.service.store.load(entry['id'])['payload']
                        source_style = self.service._style(existing)
                    except KeyError:
                        pass
                self.service.prepare(entry['id'], Path(request.source_path), cues, source_style)
                payload = self.service.store.load(entry['id'])['payload']
                payload.update(subtitle_input=str(subtitle_input.resolve()), subtitle_hash=fingerprint(subtitle_input))
                if dub:
                    payload.update(dub_audio=str(dub.resolve()), dub_hash=fingerprint(dub), duck_ratio=request.duck_ratio)
                self.service.store.save(entry['id'], payload)
                if (Path(request.project_root)/'project.json').is_file():
                    project = self.view_model.session.current_project
                    if project is not None:
                        project.settings['overlay_manifest'] = str(self.path)
                        self.view_model.session.project_service.save(project)
                ready.append(entry['id'])
            except Exception as exc:
                entry['error'] = str(exc)
            self._save()
        if ready and not self.cancel_event.is_set():
            self.service.finalize_batch('batch', tuple(ready), merge=bool(self.manifest.get('merged_output')))
        return self.rows()

    def export(self):
        self.cancel_event.clear()
        rows = self.rows()
        if not rows or any(r['payload'].get('blocking') or not self.service.store.is_approved(r['id'], r['revision']) for r in rows):
            raise ValueError('Tất cả nguồn phải được chuẩn bị và duyệt trước khi xuất/gộp.')
        results = []
        for entry, row in zip(self.manifest['items'], rows):
            if self.cancel_event.is_set():
                break
            try:
                output = self.service.render(row['id'], row['revision'], Path(entry['output']))
                results.append(BatchItemResult(Path(entry['request']['source_path']), output, Path(row['id'])))
            except Exception as exc:
                results.append(BatchItemResult(Path(entry['request']['source_path']), None, Path(row['id']), str(exc)))
        merged, merge_error = None, None
        if (self.manifest.get('merged_output') and len(results) == len(rows)
                and all(r.output_path is not None for r in results) and not self.cancel_event.is_set()):
            try:
                merged = concat_verified(tuple(r.output_path for r in results), Path(self.manifest['merged_output']),
                                         RenderProfile(**rows[0]['payload']['profile']), self.cancel_event)
            except Exception as exc:
                merge_error = str(exc)
        return BatchResult(tuple(results), merged, merge_error, self.cancel_event.is_set(), len(rows))
