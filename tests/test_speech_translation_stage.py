import json
from app.core.translation.protocol import TranslationResult
from app.providers.translation.json_contract import request_payload
from app.workers.protocol import WorkerCommand, WorkerEventType
from app.workers.runner import execute_command


def test_translation_uses_complete_speech_and_sends_real_duration(tmp_path):
    class Translator:
        def translate_batch(self, requests, target_language, glossary):
            # Fake network boundary; the persisted result proves the real
            # workflow sent speech text and a usable timing budget.
            payload = request_payload(requests, target_language, glossary)
            return [TranslationResult(r['segment_id'], r['source_text'], str(r['duration_ms']))
                    for r in payload['segments']]
    (tmp_path/'classified.json').write_text('[]')
    (tmp_path/'media.json').write_text(json.dumps({'fps':25,'duration_ms':5000}))
    (tmp_path/'asr.json').write_text(json.dumps([{'start_ms':1000,'end_ms':3000,'text':'等等陛下'}]))
    command = WorkerCommand('j','translate_events',str(tmp_path),{
        'classified_path':str(tmp_path/'classified.json'), 'media_path':str(tmp_path/'media.json'),
        'asr_path':str(tmp_path/'asr.json'), 'output_path':str(tmp_path/'translated.json')})
    events = execute_command(command, dependencies={'translation_provider':Translator()})
    assert events[-1].type is WorkerEventType.COMPLETED, events[-1].message
    result = json.loads((tmp_path/'translated.json').read_text())
    assert len(result) == 1
    assert result[0]['source_text'] == '等等陛下'
    assert result[0]['target_text'] == '2000'
    assert (result[0]['start_ms'], result[0]['end_ms']) == (1000,3000)
