"""Ghep cac doan giong roi thanh mot track dai bang video.

atempo tra ve do dai lech vai mili-giay so voi muc tieu, nen viec cat/dem
toi dung so mau cua khung o day moi la thu bien "ep vua tuyet doi" thanh
dam bao that chu khong phai xap xi.
"""
from __future__ import annotations

import wave

import numpy as np

from app.core.dubbing.track import TrackSegment, build_track, write_wav

RATE = 1000  # 1 mau = 1 ms, cho phep so sanh bang so nguyen


def _tone(length_ms, value):
    return np.full(length_ms, value, dtype=np.int16)


def test_track_length_matches_video_duration():
    track = build_track([], total_ms=2000, sample_rate=RATE)
    assert len(track) == 2000
    assert not track.any()


def test_segment_lands_at_its_start_offset():
    segment = TrackSegment(start_ms=500, end_ms=1000, samples=_tone(500, 4000))
    track = build_track([segment], total_ms=2000, sample_rate=RATE)
    assert not track[:500].any()
    assert track[600] > 0
    assert not track[1000:].any()


def test_long_segment_is_trimmed_to_exactly_its_window():
    segment = TrackSegment(start_ms=0, end_ms=500, samples=_tone(1500, 4000))
    track = build_track([segment], total_ms=2000, sample_rate=RATE)
    assert track[100] > 0
    assert not track[500:].any()


def test_short_segment_is_padded_with_silence():
    segment = TrackSegment(start_ms=0, end_ms=1000, samples=_tone(200, 4000))
    track = build_track([segment], total_ms=2000, sample_rate=RATE)
    assert track[100] > 0
    assert not track[300:].any()


def test_gap_between_segments_stays_silent():
    segments = [
        TrackSegment(start_ms=0, end_ms=400, samples=_tone(400, 4000)),
        TrackSegment(start_ms=1200, end_ms=1600, samples=_tone(400, 4000)),
    ]
    track = build_track(segments, total_ms=2000, sample_rate=RATE)
    assert not track[400:1200].any()
    assert track[1300] > 0


def test_overlapping_windows_clip_the_earlier_segment():
    segments = [
        TrackSegment(start_ms=0, end_ms=1000, samples=_tone(1000, 4000)),
        TrackSegment(start_ms=500, end_ms=1500, samples=_tone(1000, -4000)),
    ]
    track = build_track(segments, total_ms=2000, sample_rate=RATE)
    assert track[100] > 0, "first segment keeps the part before the overlap"
    assert track[600] < 0, "second segment owns the overlapping region"
    assert not track[1500:].any()


def test_segments_are_placed_in_time_order_regardless_of_input_order():
    segments = [
        TrackSegment(start_ms=1200, end_ms=1600, samples=_tone(400, -4000)),
        TrackSegment(start_ms=0, end_ms=400, samples=_tone(400, 4000)),
    ]
    track = build_track(segments, total_ms=2000, sample_rate=RATE)
    assert track[100] > 0
    assert track[1300] < 0


def test_segment_past_end_of_video_is_dropped():
    segment = TrackSegment(start_ms=5000, end_ms=6000, samples=_tone(1000, 4000))
    track = build_track([segment], total_ms=2000, sample_rate=RATE)
    assert len(track) == 2000
    assert not track.any()


def test_edges_are_faded_to_avoid_clicks():
    segment = TrackSegment(start_ms=0, end_ms=1000, samples=_tone(1000, 4000))
    track = build_track([segment], total_ms=1000, sample_rate=RATE)
    assert track[0] == 0
    assert abs(int(track[2])) < abs(int(track[100]))


def test_write_wav_round_trips_as_mono_16_bit():
    track = build_track(
        [TrackSegment(start_ms=0, end_ms=1000, samples=_tone(1000, 4000))],
        total_ms=1000, sample_rate=24000,
    )
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        path = write_wav(Path(tmp) / "dub.wav", track, sample_rate=24000)
        with wave.open(str(path), "rb") as handle:
            assert handle.getnchannels() == 1
            assert handle.getsampwidth() == 2
            assert handle.getframerate() == 24000
            assert handle.getnframes() == len(track)
