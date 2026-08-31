"""Chi test phan dung lenh, khong chay ffmpeg.

Toan bo phan cham ffmpeg nam sau hai ham build_*_command thuan, nen suite
chay duoc tren may khong co ffmpeg.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.core.dubbing.decode import build_decode_command, build_stretch_command


def test_decode_command_reads_mp3_from_stdin_and_writes_raw_pcm():
    command = build_decode_command(sample_rate=24000)
    assert command[0] == "ffmpeg"
    assert command[command.index("-i") + 1] == "pipe:0"
    assert command[command.index("-ar") + 1] == "24000"
    assert command[command.index("-ac") + 1] == "1"
    assert command[command.index("-f") + 1] == "s16le"
    assert command[-1] == "pipe:1"


def test_decode_command_honours_a_custom_binary():
    command = build_decode_command(sample_rate=24000, ffmpeg="/opt/bin/ffmpeg")
    assert command[0] == "/opt/bin/ffmpeg"


def test_stretch_command_declares_the_raw_input_format():
    command = build_stretch_command(tempo=1.8, sample_rate=24000)
    assert "-f" in command
    first_format = command.index("-f")
    assert command[first_format + 1] == "s16le"
    assert command[command.index("-i") + 1] == "pipe:0"


def test_stretch_command_applies_the_chained_tempo_filter():
    command = build_stretch_command(tempo=4.0, sample_rate=24000)
    assert command[command.index("-filter:a") + 1] == "atempo=2.000000,atempo=2.000000"


def test_unity_tempo_produces_no_filter_argument():
    command = build_stretch_command(tempo=1.0, sample_rate=24000)
    assert "-filter:a" not in command


@pytest.mark.parametrize("sample_rate", [0, -1])
def test_commands_reject_invalid_sample_rate(sample_rate):
    with pytest.raises(ValueError):
        build_decode_command(sample_rate=sample_rate)
    with pytest.raises(ValueError):
        build_stretch_command(tempo=1.0, sample_rate=sample_rate)


def test_odd_length_pcm_payload_raises_decode_error(monkeypatch):
    """An odd byte count is not a whole number of 16-bit samples."""
    import subprocess

    from app.core.dubbing import decode as decode_module

    monkeypatch.setattr(decode_module.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        decode_module.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0] if a else [], 0, b"\x01\x02\x03", b""),
    )
    with pytest.raises(decode_module.DecodeError, match="3"):
        decode_module.decode_to_pcm(b"anything", sample_rate=24000)


def test_even_length_pcm_payload_decodes(monkeypatch):
    import subprocess

    from app.core.dubbing import decode as decode_module

    monkeypatch.setattr(decode_module.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        decode_module.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0] if a else [], 0, b"\x01\x02\x03\x04", b""),
    )
    result = decode_module.decode_to_pcm(b"anything", sample_rate=24000)
    assert len(result) == 2
    assert result.dtype == np.int16
