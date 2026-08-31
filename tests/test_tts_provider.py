"""edge-tts la endpoint khong chinh thuc va phu thuoc mang.

Khong test nao o day cham mang: communicate_factory duoc tiem gia. Retry
phai co that vi mot cau hong khong duoc phep giet ca job 40 phut.
"""
from __future__ import annotations

import pytest

from app.core.dubbing.protocol import SpeechSynthesisError
from app.providers.tts.edge import VOICE_FEMALE, VOICE_MALE, EdgeTTSProvider


class _FakeCommunicate:
    def __init__(self, chunks, *, fail_times=0, log=None, label=""):
        self._chunks = chunks
        self._fail_times = fail_times
        self.log = log
        self.label = label

    async def stream(self):
        if self.log is not None:
            self.log.append(self.label)
        if self._fail_times > 0:
            self._fail_times -= 1
            raise ConnectionError("simulated network drop")
        for chunk in self._chunks:
            yield chunk


def _factory(chunks, *, fail_times=0, log=None):
    state = {"remaining": fail_times}

    def build(text, voice, rate):
        should_fail = state["remaining"] > 0
        if should_fail:
            state["remaining"] -= 1
        return _FakeCommunicate(
            chunks, fail_times=1 if should_fail else 0, log=log, label=f"{voice}|{rate}|{text}"
        )

    return build


def test_synthesize_returns_concatenated_audio_chunks():
    chunks = [
        {"type": "audio", "data": b"AB"},
        {"type": "WordBoundary", "offset": 0},
        {"type": "audio", "data": b"CD"},
    ]
    provider = EdgeTTSProvider(communicate_factory=_factory(chunks))
    assert provider.synthesize("xin chao", voice=VOICE_FEMALE) == b"ABCD"


def test_synthesize_passes_voice_and_rate_through():
    log = []
    provider = EdgeTTSProvider(communicate_factory=_factory([{"type": "audio", "data": b"A"}], log=log))
    provider.synthesize("chao", voice=VOICE_MALE, rate="+10%")
    assert log == [f"{VOICE_MALE}|+10%|chao"]


def test_transient_failure_is_retried_then_succeeds():
    sleeps = []
    provider = EdgeTTSProvider(
        communicate_factory=_factory([{"type": "audio", "data": b"OK"}], fail_times=2),
        sleep=sleeps.append,
    )
    assert provider.synthesize("chao", voice=VOICE_FEMALE) == b"OK"
    assert len(sleeps) == 2, "must back off between attempts"


def test_persistent_failure_raises_after_three_attempts():
    attempts = []

    def build(text, voice, rate):
        attempts.append(text)
        return _FakeCommunicate([], fail_times=99)

    provider = EdgeTTSProvider(communicate_factory=build, sleep=lambda _seconds: None)
    with pytest.raises(SpeechSynthesisError, match="after 3 attempts"):
        provider.synthesize("chao", voice=VOICE_FEMALE)
    assert len(attempts) == 3


def test_empty_audio_response_is_treated_as_failure():
    provider = EdgeTTSProvider(
        communicate_factory=lambda text, voice, rate: _FakeCommunicate([]),
        sleep=lambda _seconds: None,
    )
    with pytest.raises(SpeechSynthesisError):
        provider.synthesize("chao", voice=VOICE_FEMALE)


@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_blank_text_is_rejected_without_calling_the_network(text):
    def build(_text, _voice, _rate):
        raise AssertionError("must not reach the network for blank text")

    provider = EdgeTTSProvider(communicate_factory=build)
    with pytest.raises(SpeechSynthesisError):
        provider.synthesize(text, voice=VOICE_FEMALE)
