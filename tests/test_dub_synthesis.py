"""Stage synthesize_speech: chua loi o muc tung cau.

Mot cau hong khong duoc phep giet ca job 40 phut, nhung toan bo cau hong
nghia la mang chet han va phai bao that.
"""
from __future__ import annotations

import json
import wave
from pathlib import Path

import numpy as np

from app.core.dubbing.protocol import SpeechSynthesisError
from app.workers.protocol import WorkerCommand, WorkerEventType
from app.workers.runner import execute_command

RATE = 24000


class _FakeSynthesizer:
    def __init__(self, *, fail_ids=()):
        self.fail_ids = set(fail_ids)
        self.calls = []

    def synthesize(self, text, *, voice, rate="+0%"):
        self.calls.append((text, voice, rate))
        if text in self.fail_ids:
            raise SpeechSynthesisError("simulated failure")
        return text.encode("utf-8")


class _FakeCodec:
    """Turns the fake "audio" bytes into a constant tone of a known length."""

    def __init__(self, *, natural_ms=1000):
        self.natural_ms = natural_ms

    def decode(self, audio, *, sample_rate):
        length = int(self.natural_ms * sample_rate / 1000)
        return np.full(length, 4000, dtype=np.int16)

    def stretch(self, samples, *, tempo, sample_rate):
        length = max(1, int(round(len(samples) / tempo)))
        return np.full(length, samples[0] if len(samples) else 0, dtype=np.int16)


def _write_source_audio(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    t = np.arange(RATE * 4, dtype=np.float64) / RATE
    tone = (8000 * np.sin(2 * np.pi * 120.0 * t)).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(tone.tobytes())


def _project(tmp_path, segments):
    root = tmp_path / "project"
    (root / "cache" / "translation").mkdir(parents=True)
    (root / "cache" / "frames").mkdir(parents=True)
    (root / "cache" / "translation" / "translated_vi.json").write_text(
        json.dumps(segments, ensure_ascii=False), encoding="utf-8"
    )
    (root / "cache" / "frames" / "media.json").write_text(
        json.dumps({"duration_ms": 4000, "fps": 25.0}), encoding="utf-8"
    )
    _write_source_audio(root / "cache" / "audio" / "source.wav")
    return root


def _command(root):
    return WorkerCommand("job-1", "synthesize_speech", str(root), {
        "translated_path": str(root / "cache" / "translation" / "translated_vi.json"),
        "source_audio_path": str(root / "cache" / "audio" / "source.wav"),
        "media_path": str(root / "cache" / "frames" / "media.json"),
        "output_path": str(root / "cache" / "dub" / "dub_vi.wav"),
        "report_path": str(root / "cache" / "dub" / "dub-report.json"),
        "sample_rate": RATE,
        "concurrency": 2,
    })


SEGMENTS = [
    {"id": "a", "start_ms": 0, "end_ms": 1000, "target_text": "cau mot"},
    {"id": "b", "start_ms": 1500, "end_ms": 2000, "target_text": "cau hai"},
    {"id": "c", "start_ms": 2500, "end_ms": 3500, "target_text": "cau ba"},
]


def test_stage_writes_a_track_as_long_as_the_video(tmp_path):
    root = _project(tmp_path, SEGMENTS)
    events = execute_command(_command(root), dependencies={
        "speech_synthesizer": _FakeSynthesizer(), "pcm_codec": _FakeCodec(),
    })
    assert events[-1].type is WorkerEventType.COMPLETED, events[-1].message
    with wave.open(str(root / "cache" / "dub" / "dub_vi.wav"), "rb") as handle:
        assert handle.getnframes() == RATE * 4
        assert handle.getnchannels() == 1
        assert handle.getframerate() == RATE


def test_low_pitched_source_selects_the_male_voice(tmp_path):
    root = _project(tmp_path, SEGMENTS)
    synth = _FakeSynthesizer()
    execute_command(_command(root), dependencies={"speech_synthesizer": synth, "pcm_codec": _FakeCodec()})
    assert {call[1] for call in synth.calls} == {"vi-VN-NamMinhNeural"}


def test_report_records_tempo_and_flags_rushed_lines(tmp_path):
    root = _project(tmp_path, SEGMENTS)
    execute_command(_command(root), dependencies={
        "speech_synthesizer": _FakeSynthesizer(), "pcm_codec": _FakeCodec(natural_ms=1000),
    })
    report = json.loads((root / "cache" / "dub" / "dub-report.json").read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in report["segments"]}
    assert by_id["a"]["tempo"] == 1.0
    assert by_id["a"]["rushed"] is False
    # Use the silent gap before the next sentence instead of doubling speed.
    assert by_id["b"]["tempo"] == 1.0
    assert by_id["b"]["rushed"] is False
    assert by_id["b"]["end_ms"] == 2500
    assert report["rushed_count"] == 0


def test_impossible_timing_fails_instead_of_accelerating_or_truncating(tmp_path):
    root = _project(tmp_path, SEGMENTS)
    events = execute_command(_command(root), dependencies={
        "speech_synthesizer": _FakeSynthesizer(), "pcm_codec": _FakeCodec(natural_ms=19000),
    })
    assert events[-1].type is WorkerEventType.FAILED
    assert not (root / 'cache/dub/dub_vi.wav').exists()


def test_timing_rescue_allows_speech_up_to_two_x_speed(tmp_path):
    root = _project(tmp_path, [
        {"id": "tight", "start_ms": 0, "end_ms": 600, "target_text": "Ibu Suri"},
        {"id": "next", "start_ms": 600, "end_ms": 1200, "target_text": "Berikutnya"},
    ])
    events = execute_command(_command(root), dependencies={
        "speech_synthesizer": _FakeSynthesizer(), "pcm_codec": _FakeCodec(natural_ms=1000),
    })

    assert events[-1].type is WorkerEventType.COMPLETED, events[-1].message
    report = json.loads((root / "cache" / "dub" / "dub-report.json").read_text(encoding="utf-8"))
    tight = next(item for item in report["segments"] if item["id"] == "tight")
    assert tight["failed"] is False
    assert tight["tempo"] == 1.667


def test_one_unrecoverable_timing_line_is_silent_without_failing_video(tmp_path):
    class OneLongLineCodec(_FakeCodec):
        def decode(self, audio, *, sample_rate):
            self.natural_ms = 19000 if audio.decode() == "cau hai" else 1000
            return super().decode(audio, sample_rate=sample_rate)

    root = _project(tmp_path, SEGMENTS)
    events = execute_command(_command(root), dependencies={
        "speech_synthesizer": _FakeSynthesizer(), "pcm_codec": OneLongLineCodec(),
    })

    assert events[-1].type is WorkerEventType.COMPLETED, events[-1].message
    report = json.loads((root / "cache" / "dub" / "dub-report.json").read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in report["segments"]}
    assert by_id["b"]["failed"] is True
    assert report["failed_count"] == 1


def test_natural_short_speech_is_not_stretched_to_fill_silence(tmp_path):
    root = _project(tmp_path, SEGMENTS)
    events = execute_command(_command(root), dependencies={
        "speech_synthesizer": _FakeSynthesizer(), "pcm_codec": _FakeCodec(natural_ms=200),
    })
    assert events[-1].type is WorkerEventType.COMPLETED
    with wave.open(str(root / 'cache/dub/dub_vi.wav'), 'rb') as f:
        f.setpos(int(.5 * RATE))
        assert not np.frombuffer(f.readframes(100), dtype='<i2').any()


def test_shortening_updates_subtitle_to_exact_spoken_text(tmp_path):
    from app.core.translation.protocol import TranslationResult
    class Translator:
        def translate_batch(self, requests, target_language, glossary):
            return [TranslationResult(requests[0].segment_id, 'Câu nói đầy đủ', 'Xin chào')]
    class Codec(_FakeCodec):
        def decode(self, audio, *, sample_rate):
            self.natural_ms = 500 if audio.decode() == 'Xin chào' else 5000
            return super().decode(audio, sample_rate=sample_rate)
    root = _project(tmp_path, [{'id':'a', 'start_ms':0, 'end_ms':1000,
                              'source_text':'你好', 'target_text':'Xin chào tất cả mọi người'}])
    command = _command(root)
    command.config['translation_config'] = {'translation_provider':'openai'}
    events = execute_command(command, dependencies={'speech_synthesizer':_FakeSynthesizer(),
        'pcm_codec':Codec(), 'translation_provider':Translator()})
    assert events[-1].type is WorkerEventType.COMPLETED, events[-1].message
    captions = json.loads((root/'cache/translation/translated_vi.json').read_text())
    assert captions[0]['target_text'] == 'Xin chào'
    assert captions[0]['optimized_translation'] == 'Xin chào'
    report = json.loads((root/'cache/dub/dub-report.json').read_text())
    assert captions[0]['end_ms'] == report['segments'][0]['end_ms']
    assert report['segments'][0]['tempo'] <= 1.35


def test_encoder_padding_does_not_force_fast_speech(tmp_path):
    class PaddedCodec(_FakeCodec):
        def decode(self, audio, *, sample_rate):
            # A 400ms utterance surrounded by encoder/service silence.
            return np.concatenate([np.zeros(RATE, dtype=np.int16),
                np.full(int(.4 * RATE), 4000, dtype=np.int16), np.zeros(RATE * 2, dtype=np.int16)])
    root = _project(tmp_path, [{'id':'a','start_ms':0,'end_ms':500,'target_text':'Chào'}])
    events = execute_command(_command(root), dependencies={
        'speech_synthesizer':_FakeSynthesizer(), 'pcm_codec':PaddedCodec()})
    assert events[-1].type is WorkerEventType.COMPLETED, events[-1].message
    report = json.loads((root/'cache/dub/dub-report.json').read_text())
    assert report['segments'][0]['tempo'] == 1.0


def test_regenerating_speech_does_not_borrow_pause_twice(tmp_path):
    root = _project(tmp_path, [{'id':'a','start_ms':0,'end_ms':1000,'target_text':'Xin chào'}])
    first = execute_command(_command(root), dependencies={
        'speech_synthesizer':_FakeSynthesizer(), 'pcm_codec':_FakeCodec(natural_ms=2000)})
    assert first[-1].type is WorkerEventType.COMPLETED
    second = execute_command(_command(root), dependencies={
        'speech_synthesizer':_FakeSynthesizer(), 'pcm_codec':_FakeCodec(natural_ms=5000)})
    assert second[-1].type is WorkerEventType.FAILED


def test_one_failed_line_leaves_its_window_silent_but_completes(tmp_path):
    root = _project(tmp_path, SEGMENTS)
    events = execute_command(_command(root), dependencies={
        "speech_synthesizer": _FakeSynthesizer(fail_ids={"cau hai"}), "pcm_codec": _FakeCodec(),
    })
    assert events[-1].type is WorkerEventType.COMPLETED
    # StageEvent (what the UI actually receives) has no `data` field, so a
    # partial failure must be visible in the message text, not just the dict.
    assert "1 failed" in events[-1].message
    report = json.loads((root / "cache" / "dub" / "dub-report.json").read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in report["segments"]}
    assert by_id["b"]["failed"] is True
    assert by_id["a"]["failed"] is False
    assert report["failed_count"] == 1
    with wave.open(str(root / "cache" / "dub" / "dub_vi.wav"), "rb") as handle:
        handle.setpos(int(1.6 * RATE))
        window = np.frombuffer(handle.readframes(int(0.2 * RATE)), dtype="<i2")
    assert not window.any(), "failed line must leave silence, not noise"


def test_every_line_failing_fails_the_stage(tmp_path):
    root = _project(tmp_path, SEGMENTS)
    events = execute_command(_command(root), dependencies={
        "speech_synthesizer": _FakeSynthesizer(fail_ids={"cau mot", "cau hai", "cau ba"}),
        "pcm_codec": _FakeCodec(),
    })
    assert events[-1].type is WorkerEventType.FAILED
    assert "every" in events[-1].message.lower() or "all" in events[-1].message.lower()


def test_empty_translation_completes_with_a_silent_track(tmp_path):
    root = _project(tmp_path, [])
    events = execute_command(_command(root), dependencies={
        "speech_synthesizer": _FakeSynthesizer(), "pcm_codec": _FakeCodec(),
    })
    assert events[-1].type is WorkerEventType.COMPLETED
    with wave.open(str(root / "cache" / "dub" / "dub_vi.wav"), "rb") as handle:
        assert handle.getnframes() == RATE * 4


def test_blank_target_text_is_skipped_without_calling_the_synthesizer(tmp_path):
    root = _project(tmp_path, [{"id": "a", "start_ms": 0, "end_ms": 1000, "target_text": "   "}])
    synth = _FakeSynthesizer()
    events = execute_command(_command(root), dependencies={
        "speech_synthesizer": synth, "pcm_codec": _FakeCodec(),
    })
    assert events[-1].type is WorkerEventType.COMPLETED
    assert synth.calls == []
