# Lồng tiếng Việt + bỏ xoá phụ đề Trung — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm lồng tiếng Việt tự phân giọng nam/nữ vào pipeline, và bỏ bước xoá phụ đề Trung khỏi đường chạy mặc định bằng cách đặt phụ đề Việt ngay dưới dải chữ Trung.

**Architecture:** Một stage worker mới `synthesize_speech` nằm giữa `translate_events` và `render_final`, sinh ra một track PCM dài bằng video rồi để `render_final` trộn ducking bằng `sidechaincompress`. Stage `erase_video` trở thành tuỳ chọn; khi tắt, `render_final` đọc thẳng video gốc và `write_ass` chuyển sang neo `\an8` ngay dưới đáy bbox chữ Trung. Toàn bộ luật nằm trong hàm thuần ở `app/core/`, mọi thứ chạm mạng hoặc chạm ffmpeg nằm sau Protocol/command-builder để test không cần cả hai.

**Tech Stack:** Python 3.11–3.13, numpy, edge-tts, ffmpeg 8.x (`atempo`, `sidechaincompress`, `amix`, `ass`), PySide6, pytest.

**Spec:** `docs/superpowers/specs/2026-08-31-vietnamese-dubbing-design.md`

**Nhánh:** `feat/vietnamese-dubbing` (đã tạo, đã có commit spec `d418c6f`)

## Global Constraints

Mọi task đều phải thoả các ràng buộc dưới đây.

- **Không test nào chạm mạng. Không test nào chạy ffmpeg.** Chạm mạng nằm sau `SpeechSynthesizer` Protocol; chạm ffmpeg nằm sau các hàm `build_*_command` thuần. Test dùng fake tiêm qua tham số `dependencies` của `execute_command`.
- **Không thêm dependency runtime nào ngoài `edge-tts`.** `numpy` đã có sẵn trong `[project].dependencies`; `wave`, `asyncio`, `concurrent.futures`, `math` là stdlib.
- Python `>=3.11,<3.14`. Mọi file mới bắt đầu bằng `from __future__ import annotations`.
- Track lồng tiếng: **mono, 24000 Hz, int16**.
- `atempo`: mọi tầng phải nằm trong `[0.5, 2.0]`; tích các tầng bằng đúng tempo yêu cầu.
- Ngưỡng F0: nam `< 155.0` Hz, nữ `> 190.0` Hz, vùng chết `155.0–190.0` → giọng mặc định.
- Hằng số đặt phụ đề: `gap_ratio=0.45`, `line_height=1.2`, `min_font_scale=0.78`, `bottom_safe_ratio=0.02`.
- `duck_ratio`: Nhẹ = `6`, Vừa = `12`, Mạnh = `20`.
- `rushed_tempo` mặc định `1.5`; `concurrency` mặc định `4`; retry TTS `3` lần.
- Giọng mặc định: nữ `vi-VN-HoaiMyNeural`, nam `vi-VN-NamMinhNeural`.
- Mặc định UI: lồng tiếng **BẬT**, xoá phụ đề **TẮT**.
- Style: `outline_width=2.5`, `shadow=1.0`.
- Chạy test bằng `.venv/bin/python -m pytest` từ gốc repo.
- **Mọi commit** dùng conventional commit và kết thúc bằng hai dòng trailer:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FPVybnTqANCD1rXXcgthWQ
```

## Bản đồ file

| File | Trách nhiệm | Task |
|---|---|---|
| `app/core/dubbing/timing.py` | Tính tempo và tách chuỗi `atempo` | 1 |
| `app/core/dubbing/voice.py` | Đo F0 từ wav, chọn giọng nam/nữ | 2 |
| `app/core/dubbing/track.py` | Ghép các đoạn PCM thành một track dài, ghi wav | 3 |
| `app/core/dubbing/protocol.py` | `SpeechSynthesizer` Protocol + lớp lỗi | 4 |
| `app/providers/tts/edge.py` | Gọi edge-tts, retry có backoff | 4 |
| `app/core/dubbing/decode.py` | Dựng lệnh ffmpeg giải mã/kéo giãn PCM | 5 |
| `app/workers/runner.py` | Stage `synthesize_speech`; `render_final` nhận placement + dub | 6, 9 |
| `app/core/rendering/placement.py` | Tính vị trí phụ đề dưới dải chữ Trung | 7 |
| `app/core/rendering/ass.py` | Phát `\an8\pos` theo chế độ placement | 8 |
| `app/core/rendering/style.py` | Viền/bóng dày hơn | 8 |
| `app/core/rendering/renderer.py` | Dựng filtergraph ducking, trả báo cáo vị trí | 9 |
| `app/application/default_workflow.py` | Bỏ/giữ `erase_video`, chèn `synthesize_speech` | 10 |
| `app/application/view_model.py` | `ProjectStartRequest` mới, `_dub_config`, preflight | 11 |
| `app/application/session.py` | Chuyển tham số mới xuống workflow | 11 |
| `app/ui/project_setup.py` | Các ô điều khiển mới | 12 |
| `app/ui/main_window.py` | Đọc form → request | 12 |
| `app/ui/processing_view.py` | Thêm stage vào thanh tiến trình | 12 |
| `app/cli.py` | Cờ dòng lệnh mới | 13 |
| `pyproject.toml`, `installers/*`, `run-*.sh` | Extra `dub` | 13 |

---

### Task 1: Tính tempo và chuỗi `atempo`

**Files:**
- Create: `app/core/dubbing/__init__.py`
- Create: `app/core/dubbing/timing.py`
- Test: `tests/test_dub_timing.py`

**Interfaces:**
- Consumes: không
- Produces:
  - `fit_tempo(natural_ms: int, window_ms: int) -> float`
  - `atempo_chain(tempo: float) -> tuple[float, ...]`
  - `atempo_filter(tempo: float) -> str`
  - Hằng: `TEMPO_MIN = 0.5`, `TEMPO_MAX = 2.0`, `TEMPO_EPSILON = 1e-3`

- [ ] **Step 1: Viết test hỏng**

Tạo `tests/test_dub_timing.py`:

```python
"""Ep giong Viet vua khung thoi gian cua phu de goc.

atempo cua ffmpeg nhan 0.5-100 trong mot tang, nhung vuot 2x mot lan thi
meo tieng ro. Chuoi nhieu tang giu moi tang trong [0.5, 2.0] ma tich van
bang dung tempo yeu cau.
"""
from __future__ import annotations

import math

import pytest

from app.core.dubbing.timing import (
    TEMPO_MAX,
    TEMPO_MIN,
    atempo_chain,
    atempo_filter,
    fit_tempo,
)


def test_fit_tempo_is_ratio_of_natural_to_window():
    assert fit_tempo(3000, 1500) == pytest.approx(2.0)
    assert fit_tempo(750, 1500) == pytest.approx(0.5)


@pytest.mark.parametrize("natural_ms,window_ms", [(0, 1000), (-1, 1000), (1000, 0), (1000, -5)])
def test_fit_tempo_rejects_non_positive(natural_ms, window_ms):
    with pytest.raises(ValueError):
        fit_tempo(natural_ms, window_ms)


def test_unity_tempo_needs_no_filter():
    assert atempo_chain(1.0) == ()
    assert atempo_filter(1.0) == ""


def test_tempo_inside_safe_range_uses_one_stage():
    assert atempo_chain(1.8) == pytest.approx((1.8,))
    assert atempo_chain(0.5) == pytest.approx((0.5,))
    assert atempo_chain(2.0) == pytest.approx((2.0,))


def test_fast_tempo_splits_into_two_stages():
    stages = atempo_chain(2.33)
    assert len(stages) == 2
    assert math.prod(stages) == pytest.approx(2.33)


def test_slow_tempo_splits_into_two_stages():
    stages = atempo_chain(0.3)
    assert len(stages) == 2
    assert math.prod(stages) == pytest.approx(0.3)


def test_very_fast_tempo_splits_into_three_stages():
    stages = atempo_chain(5.0)
    assert len(stages) == 3
    assert math.prod(stages) == pytest.approx(5.0)


@pytest.mark.parametrize(
    "tempo",
    [0.12, 0.25, 0.3, 0.49, 0.5, 0.9, 1.1, 1.8, 2.0, 2.01, 2.33, 4.0, 5.0, 9.9],
)
def test_every_stage_stays_in_ffmpeg_safe_range(tempo):
    stages = atempo_chain(tempo)
    assert stages, "non-unity tempo must produce at least one stage"
    assert all(TEMPO_MIN <= stage <= TEMPO_MAX for stage in stages), stages
    assert math.prod(stages) == pytest.approx(tempo)


def test_atempo_filter_joins_stages_for_ffmpeg():
    assert atempo_filter(1.8) == "atempo=1.800000"
    assert atempo_filter(4.0) == "atempo=2.000000,atempo=2.000000"


@pytest.mark.parametrize("tempo", [0.0, -1.0])
def test_atempo_chain_rejects_non_positive(tempo):
    with pytest.raises(ValueError):
        atempo_chain(tempo)
```

- [ ] **Step 2: Chạy test để xác nhận nó hỏng**

Run: `.venv/bin/python -m pytest tests/test_dub_timing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.dubbing'`

- [ ] **Step 3: Viết implementation tối thiểu**

Tạo `app/core/dubbing/__init__.py` (file rỗng).

Tạo `app/core/dubbing/timing.py`:

```python
"""Fit synthesized Vietnamese speech into the source subtitle's time window."""
from __future__ import annotations

import math

# ffmpeg's atempo accepts 0.5-100 in a single stage, but anything past 2x in
# one pass smears transients audibly. Chaining stages of tempo**(1/n) keeps the
# same overall factor with far less artifacting.
TEMPO_MIN = 0.5
TEMPO_MAX = 2.0
TEMPO_EPSILON = 1e-3


def fit_tempo(natural_ms: int, window_ms: int) -> float:
    """Tempo factor that squeezes natural speech into the subtitle window."""
    if natural_ms <= 0:
        raise ValueError("natural_ms must be positive")
    if window_ms <= 0:
        raise ValueError("window_ms must be positive")
    return float(natural_ms) / float(window_ms)


def atempo_chain(tempo: float) -> tuple[float, ...]:
    """Split a tempo factor into stages that each stay within ffmpeg's sweet spot."""
    if tempo <= 0:
        raise ValueError("tempo must be positive")
    if abs(tempo - 1.0) < TEMPO_EPSILON:
        return ()
    if TEMPO_MIN <= tempo <= TEMPO_MAX:
        return (float(tempo),)
    reach = tempo if tempo > TEMPO_MAX else 1.0 / tempo
    stages = max(2, math.ceil(math.log2(reach)))
    factor = tempo ** (1.0 / stages)
    return tuple([factor] * stages)


def atempo_filter(tempo: float) -> str:
    """ffmpeg filter fragment for a tempo factor, or "" when no change is needed."""
    return ",".join(f"atempo={stage:.6f}" for stage in atempo_chain(tempo))
```

- [ ] **Step 4: Chạy test để xác nhận nó pass**

Run: `.venv/bin/python -m pytest tests/test_dub_timing.py -v`
Expected: PASS — tất cả test xanh.

- [ ] **Step 5: Commit**

```bash
git add app/core/dubbing/__init__.py app/core/dubbing/timing.py tests/test_dub_timing.py
git commit -m "feat(dubbing): fit speech tempo with chained atempo stages"
```

---

### Task 2: Chọn giọng nam/nữ theo cao độ

**Files:**
- Create: `app/core/dubbing/voice.py`
- Test: `tests/test_dub_voice.py`

**Interfaces:**
- Consumes: không
- Produces:
  - `read_slice(path: Path, start_ms: int, end_ms: int) -> tuple[np.ndarray, int]` — trả `(samples float32 mono, sample_rate)`
  - `estimate_f0(samples: np.ndarray, sample_rate: int) -> float` — trả `0.0` khi không xác định được
  - `choose_gender(f0_hz: float) -> str` — trả `"male"` / `"female"` / `"default"`
  - Hằng: `MALE_MAX_HZ = 155.0`, `FEMALE_MIN_HZ = 190.0`

- [ ] **Step 1: Viết test hỏng**

Tạo `tests/test_dub_voice.py`:

```python
"""Phan giong nam/nu bang cao do giong goc, khong dung model nao.

Nam ~85-155Hz, nu ~165-255Hz. Vung 155-190Hz la cho giong nu tram va giong
nam cao chong nhau: doan bua o do cho ket qua lat qua lat lai giua cac cau
lien tiep, kho chiu hon han so voi roi ve mot giong on dinh.
"""
from __future__ import annotations

import wave

import numpy as np
import pytest

from app.core.dubbing.voice import (
    FEMALE_MIN_HZ,
    MALE_MAX_HZ,
    choose_gender,
    estimate_f0,
    read_slice,
)

RATE = 16000


def _write_wav(path, samples):
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(samples.astype("<i2").tobytes())
    return path


def _tone(freq, *, duration_s=1.0, amplitude=8000):
    t = np.arange(int(RATE * duration_s), dtype=np.float64) / RATE
    return amplitude * np.sin(2 * np.pi * freq * t)


def test_male_pitch_maps_to_male_voice(tmp_path):
    path = _write_wav(tmp_path / "male.wav", _tone(120.0))
    samples, rate = read_slice(path, 0, 1000)
    f0 = estimate_f0(samples, rate)
    assert f0 == pytest.approx(120.0, rel=0.05)
    assert choose_gender(f0) == "male"


def test_female_pitch_maps_to_female_voice(tmp_path):
    path = _write_wav(tmp_path / "female.wav", _tone(220.0))
    samples, rate = read_slice(path, 0, 1000)
    f0 = estimate_f0(samples, rate)
    assert f0 == pytest.approx(220.0, rel=0.05)
    assert choose_gender(f0) == "female"


def test_dead_band_pitch_falls_back_to_default(tmp_path):
    path = _write_wav(tmp_path / "ambiguous.wav", _tone(170.0))
    samples, rate = read_slice(path, 0, 1000)
    f0 = estimate_f0(samples, rate)
    assert MALE_MAX_HZ <= f0 <= FEMALE_MIN_HZ
    assert choose_gender(f0) == "default"


def test_silence_yields_no_pitch(tmp_path):
    path = _write_wav(tmp_path / "silence.wav", np.zeros(RATE))
    samples, rate = read_slice(path, 0, 1000)
    assert estimate_f0(samples, rate) == 0.0
    assert choose_gender(0.0) == "default"


def test_white_noise_is_not_mistaken_for_speech(tmp_path):
    rng = np.random.default_rng(0)
    noise = rng.normal(0.0, 3000.0, RATE)
    path = _write_wav(tmp_path / "noise.wav", noise)
    samples, rate = read_slice(path, 0, 1000)
    assert estimate_f0(samples, rate) == 0.0
    assert choose_gender(0.0) == "default"


def test_read_slice_extracts_only_the_requested_window(tmp_path):
    path = _write_wav(tmp_path / "long.wav", _tone(120.0, duration_s=3.0))
    samples, rate = read_slice(path, 1000, 2000)
    assert rate == RATE
    assert len(samples) == RATE


def test_read_slice_clamps_past_end_of_file(tmp_path):
    path = _write_wav(tmp_path / "short.wav", _tone(120.0, duration_s=0.5))
    samples, _ = read_slice(path, 0, 5000)
    assert len(samples) == RATE // 2


def test_read_slice_downmixes_stereo(tmp_path):
    path = tmp_path / "stereo.wav"
    mono = _tone(120.0).astype("<i2")
    stereo = np.repeat(mono, 2)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(stereo.tobytes())
    samples, rate = read_slice(path, 0, 1000)
    assert len(samples) == RATE
    assert estimate_f0(samples, rate) == pytest.approx(120.0, rel=0.05)


@pytest.mark.parametrize(
    "f0,expected",
    [(90.0, "male"), (154.9, "male"), (155.0, "default"), (190.0, "default"),
     (190.1, "female"), (250.0, "female"), (0.0, "default")],
)
def test_gender_boundaries(f0, expected):
    assert choose_gender(f0) == expected
```

- [ ] **Step 2: Chạy test để xác nhận nó hỏng**

Run: `.venv/bin/python -m pytest tests/test_dub_voice.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.dubbing.voice'`

- [ ] **Step 3: Viết implementation tối thiểu**

Tạo `app/core/dubbing/voice.py`:

```python
"""Pick a dub voice from the pitch of the original speaker.

Autocorrelation on the already-extracted source audio is enough to separate
male from female fundamentals, so this needs no model, no download, and no
HuggingFace token. Speaker diarization would tell us who is talking but not
their vocal range, which is the only thing the voice choice depends on.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

MALE_MAX_HZ = 155.0
FEMALE_MIN_HZ = 190.0

F0_MIN_HZ = 70.0
F0_MAX_HZ = 320.0
FRAME_MS = 40
HOP_MS = 20
MIN_VOICED_FRAMES = 5
VOICED_CORRELATION = 0.3
SILENCE_RMS = 200.0


def read_slice(path: str | Path, start_ms: int, end_ms: int) -> tuple[np.ndarray, int]:
    """Read one time window of a 16-bit PCM wav as mono float samples."""
    with wave.open(str(path), "rb") as handle:
        if handle.getsampwidth() != 2:
            raise ValueError("source audio must be 16-bit PCM")
        rate = handle.getframerate()
        channels = handle.getnchannels()
        total = handle.getnframes()
        start = max(0, min(total, int(start_ms * rate / 1000)))
        end = max(start, min(total, int(end_ms * rate / 1000)))
        handle.setpos(start)
        raw = handle.readframes(end - start)
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32)
    if channels > 1:
        usable = (len(samples) // channels) * channels
        samples = samples[:usable].reshape(-1, channels).mean(axis=1)
    return samples, rate


def _frame_f0(frame: np.ndarray, sample_rate: int) -> float:
    centred = frame - frame.mean()
    if float(np.sqrt(np.mean(np.square(centred)))) < SILENCE_RMS:
        return 0.0
    correlation = np.correlate(centred, centred, mode="full")[len(centred) - 1:]
    if correlation[0] <= 0.0:
        return 0.0
    correlation = correlation / correlation[0]
    min_lag = int(sample_rate / F0_MAX_HZ)
    max_lag = int(sample_rate / F0_MIN_HZ)
    if min_lag < 1 or max_lag <= min_lag or max_lag >= len(correlation):
        return 0.0
    window = correlation[min_lag:max_lag]
    peak = int(np.argmax(window))
    # An unvoiced frame's autocorrelation decays without a clear periodic peak,
    # which is what separates speech from noise and room tone here.
    if window[peak] < VOICED_CORRELATION:
        return 0.0
    return float(sample_rate) / float(min_lag + peak)


def estimate_f0(samples: np.ndarray, sample_rate: int) -> float:
    """Median fundamental frequency over voiced frames; 0.0 when undetermined."""
    frame_length = int(sample_rate * FRAME_MS / 1000)
    hop = int(sample_rate * HOP_MS / 1000)
    if frame_length <= 0 or hop <= 0 or len(samples) < frame_length:
        return 0.0
    voiced = [
        value
        for start in range(0, len(samples) - frame_length + 1, hop)
        if (value := _frame_f0(samples[start:start + frame_length], sample_rate)) > 0.0
    ]
    if len(voiced) < MIN_VOICED_FRAMES:
        return 0.0
    return float(np.median(voiced))


def choose_gender(f0_hz: float) -> str:
    """Map a fundamental frequency to "male", "female", or "default"."""
    if f0_hz <= 0.0:
        return "default"
    if f0_hz < MALE_MAX_HZ:
        return "male"
    if f0_hz > FEMALE_MIN_HZ:
        return "female"
    return "default"
```

- [ ] **Step 4: Chạy test để xác nhận nó pass**

Run: `.venv/bin/python -m pytest tests/test_dub_voice.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/dubbing/voice.py tests/test_dub_voice.py
git commit -m "feat(dubbing): choose dub voice from source speaker pitch"
```

---

### Task 3: Ghép các đoạn thành một track dài

**Files:**
- Create: `app/core/dubbing/track.py`
- Test: `tests/test_dub_track.py`

**Interfaces:**
- Consumes: không
- Produces:
  - `TrackSegment` dataclass: `start_ms: int`, `end_ms: int`, `samples: np.ndarray` (int16 mono)
  - `build_track(segments: Sequence[TrackSegment], *, total_ms: int, sample_rate: int) -> np.ndarray`
  - `write_wav(path: Path, track: np.ndarray, *, sample_rate: int) -> Path`
  - Hằng: `FADE_MS = 5`

- [ ] **Step 1: Viết test hỏng**

Tạo `tests/test_dub_track.py`:

```python
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
```

- [ ] **Step 2: Chạy test để xác nhận nó hỏng**

Run: `.venv/bin/python -m pytest tests/test_dub_track.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.dubbing.track'`

- [ ] **Step 3: Viết implementation tối thiểu**

Tạo `app/core/dubbing/track.py`:

```python
"""Assemble per-line speech clips into one narration track."""
from __future__ import annotations

import wave
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

FADE_MS = 5


@dataclass(frozen=True, slots=True)
class TrackSegment:
    start_ms: int
    end_ms: int
    samples: np.ndarray


def _fit_window(samples: np.ndarray, window_samples: int) -> np.ndarray:
    """Trim or pad to exactly the window length.

    atempo lands a few milliseconds off its target, so this is where the
    absolute-fit guarantee is actually enforced.
    """
    if len(samples) >= window_samples:
        return samples[:window_samples].astype(np.int16)
    padded = np.zeros(window_samples, dtype=np.int16)
    padded[: len(samples)] = samples
    return padded


def _apply_fade(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    fade = min(int(sample_rate * FADE_MS / 1000), len(samples) // 2)
    if fade <= 0:
        return samples
    ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
    faded = samples.astype(np.float32)
    faded[:fade] *= ramp
    faded[-fade:] *= ramp[::-1]
    return faded.astype(np.int16)


def build_track(
    segments: Sequence[TrackSegment], *, total_ms: int, sample_rate: int
) -> np.ndarray:
    """Silent track of the video's length with each line placed at its own window."""
    total_samples = max(0, int(round(total_ms * sample_rate / 1000)))
    track = np.zeros(total_samples, dtype=np.int16)
    ordered = sorted(segments, key=lambda item: item.start_ms)
    for index, segment in enumerate(ordered):
        end_ms = segment.end_ms
        if index + 1 < len(ordered):
            # coalesce_dialogue_events already merges overlapping cues, but a
            # stray overlap must never let one line bleed over the next.
            end_ms = min(end_ms, ordered[index + 1].start_ms)
        start = max(0, min(total_samples, int(round(segment.start_ms * sample_rate / 1000))))
        stop = max(start, min(total_samples, int(round(end_ms * sample_rate / 1000))))
        if stop <= start:
            continue
        track[start:stop] = _apply_fade(_fit_window(segment.samples, stop - start), sample_rate)
    return track


def write_wav(path: str | Path, track: np.ndarray, *, sample_rate: int) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(track.astype("<i2").tobytes())
    return output
```

- [ ] **Step 4: Chạy test để xác nhận nó pass**

Run: `.venv/bin/python -m pytest tests/test_dub_track.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/dubbing/track.py tests/test_dub_track.py
git commit -m "feat(dubbing): assemble per-line clips into one narration track"
```

---

### Task 4: Protocol TTS và provider edge-tts

**Files:**
- Create: `app/core/dubbing/protocol.py`
- Create: `app/providers/tts/__init__.py`
- Create: `app/providers/tts/edge.py`
- Test: `tests/test_tts_provider.py`

**Interfaces:**
- Consumes: không
- Produces:
  - `SpeechSynthesisError(RuntimeError)`
  - `SpeechSynthesizer` Protocol: `synthesize(self, text: str, *, voice: str, rate: str = "+0%") -> bytes`
  - `EdgeTTSProvider(*, attempts: int = 3, sleep=time.sleep, communicate_factory=None)`
  - Hằng: `VOICE_FEMALE = "vi-VN-HoaiMyNeural"`, `VOICE_MALE = "vi-VN-NamMinhNeural"`, `DEFAULT_ATTEMPTS = 3`

- [ ] **Step 1: Viết test hỏng**

Tạo `tests/test_tts_provider.py`:

```python
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
```

- [ ] **Step 2: Chạy test để xác nhận nó hỏng**

Run: `.venv/bin/python -m pytest tests/test_tts_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.dubbing.protocol'`

- [ ] **Step 3: Viết implementation tối thiểu**

Tạo `app/core/dubbing/protocol.py`:

```python
"""Boundary between dubbing rules and whatever speaks the words."""
from __future__ import annotations

from typing import Protocol


class SpeechSynthesisError(RuntimeError):
    pass


class SpeechSynthesizer(Protocol):
    def synthesize(self, text: str, *, voice: str, rate: str = "+0%") -> bytes:
        """Return encoded audio (MP3) for one line of dialogue."""
        ...
```

Tạo `app/providers/tts/__init__.py` (file rỗng).

Tạo `app/providers/tts/edge.py`:

```python
"""Microsoft Edge neural voices, reached through the edge-tts package."""
from __future__ import annotations

import asyncio
import time

from app.core.dubbing.protocol import SpeechSynthesisError

VOICE_FEMALE = "vi-VN-HoaiMyNeural"
VOICE_MALE = "vi-VN-NamMinhNeural"

DEFAULT_ATTEMPTS = 3
BACKOFF_SECONDS = (1.0, 3.0)


class EdgeTTSProvider:
    def __init__(self, *, attempts: int = DEFAULT_ATTEMPTS, sleep=time.sleep, communicate_factory=None) -> None:
        self.attempts = max(1, int(attempts))
        self._sleep = sleep
        self._factory = communicate_factory or self._default_factory

    @staticmethod
    def _default_factory(text: str, voice: str, rate: str):
        try:
            import edge_tts
        except ImportError as exc:  # pragma: no cover - covered by preflight
            raise SpeechSynthesisError("edge-tts is not installed") from exc
        return edge_tts.Communicate(text, voice, rate=rate)

    def synthesize(self, text: str, *, voice: str, rate: str = "+0%") -> bytes:
        clean = text.strip()
        if not clean:
            raise SpeechSynthesisError("cannot synthesize empty text")
        last: Exception | None = None
        for attempt in range(self.attempts):
            try:
                return self._collect(self._factory(clean, voice, rate))
            except Exception as exc:
                last = exc
                if attempt + 1 < self.attempts:
                    self._sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
        raise SpeechSynthesisError(f"edge-tts failed after {self.attempts} attempts: {last}")

    @staticmethod
    def _collect(communicate) -> bytes:
        async def drain() -> bytes:
            audio = bytearray()
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio":
                    audio.extend(chunk["data"])
            return bytes(audio)

        audio = asyncio.run(drain())
        if not audio:
            raise SpeechSynthesisError("edge-tts returned no audio")
        return audio
```

- [ ] **Step 4: Chạy test để xác nhận nó pass**

Run: `.venv/bin/python -m pytest tests/test_tts_provider.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/dubbing/protocol.py app/providers/tts/ tests/test_tts_provider.py
git commit -m "feat(dubbing): add edge-tts speech provider with retry"
```

---

### Task 5: Lệnh ffmpeg giải mã và kéo giãn PCM

**Files:**
- Create: `app/core/dubbing/decode.py`
- Test: `tests/test_dub_decode.py`

**Interfaces:**
- Consumes: `app.core.dubbing.timing.atempo_filter` (Task 1)
- Produces:
  - `build_decode_command(*, sample_rate: int, ffmpeg: str = "ffmpeg") -> list[str]`
  - `build_stretch_command(*, tempo: float, sample_rate: int, ffmpeg: str = "ffmpeg") -> list[str]`
  - `decode_to_pcm(audio: bytes, *, sample_rate: int, ffmpeg: str = "ffmpeg") -> np.ndarray`
  - `stretch_pcm(samples: np.ndarray, *, tempo: float, sample_rate: int, ffmpeg: str = "ffmpeg") -> np.ndarray`
  - `PcmCodec` — lớp gộp hai hàm trên để tiêm vào stage; có `decode(...)` và `stretch(...)`
  - `DecodeError(RuntimeError)`

Hai lần gọi ffmpeg cho mỗi câu: lần một giải mã MP3 → PCM để **đo** độ dài tự nhiên, lần hai kéo giãn PCM → PCM theo tempo đã tính. Clip chỉ dài vài giây nên chi phí không đáng kể, và tách đôi như vậy giúp tempo được tính từ số đo thật thay vì phải đoán trước.

- [ ] **Step 1: Viết test hỏng**

Tạo `tests/test_dub_decode.py`:

```python
"""Chi test phan dung lenh, khong chay ffmpeg.

Toan bo phan cham ffmpeg nam sau hai ham build_*_command thuan, nen suite
chay duoc tren may khong co ffmpeg.
"""
from __future__ import annotations

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
```

- [ ] **Step 2: Chạy test để xác nhận nó hỏng**

Run: `.venv/bin/python -m pytest tests/test_dub_decode.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.dubbing.decode'`

- [ ] **Step 3: Viết implementation tối thiểu**

Tạo `app/core/dubbing/decode.py`:

```python
"""Turn encoded speech into PCM and stretch it to fit a subtitle window.

The command builders are pure so the whole audio path can be tested without
ffmpeg installed; only decode_to_pcm/stretch_pcm actually spawn a process.
"""
from __future__ import annotations

import shutil
import subprocess

import numpy as np

from .timing import atempo_filter


class DecodeError(RuntimeError):
    pass


def _check_sample_rate(sample_rate: int) -> None:
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")


def build_decode_command(*, sample_rate: int, ffmpeg: str = "ffmpeg") -> list[str]:
    _check_sample_rate(sample_rate)
    return [
        ffmpeg, "-hide_banner", "-loglevel", "error",
        "-i", "pipe:0",
        "-vn", "-ar", str(sample_rate), "-ac", "1",
        "-f", "s16le", "pipe:1",
    ]


def build_stretch_command(*, tempo: float, sample_rate: int, ffmpeg: str = "ffmpeg") -> list[str]:
    _check_sample_rate(sample_rate)
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error",
        "-f", "s16le", "-ar", str(sample_rate), "-ac", "1",
        "-i", "pipe:0",
    ]
    filters = atempo_filter(tempo)
    if filters:
        command += ["-filter:a", filters]
    command += ["-ar", str(sample_rate), "-ac", "1", "-f", "s16le", "pipe:1"]
    return command


def _run(command: list[str], payload: bytes) -> np.ndarray:
    binary = shutil.which(command[0])
    if binary is None:
        raise DecodeError(f"required media binary is not installed: {command[0]}")
    proc = subprocess.run([binary, *command[1:]], input=payload, capture_output=True, check=False)
    if proc.returncode != 0:
        raise DecodeError(f"ffmpeg audio conversion failed: {proc.stderr[-2000:].decode('utf-8', 'replace')}")
    return np.frombuffer(proc.stdout, dtype="<i2").astype(np.int16)


def decode_to_pcm(audio: bytes, *, sample_rate: int, ffmpeg: str = "ffmpeg") -> np.ndarray:
    return _run(build_decode_command(sample_rate=sample_rate, ffmpeg=ffmpeg), audio)


def stretch_pcm(samples: np.ndarray, *, tempo: float, sample_rate: int, ffmpeg: str = "ffmpeg") -> np.ndarray:
    if not atempo_filter(tempo):
        return samples.astype(np.int16)
    payload = samples.astype("<i2").tobytes()
    return _run(build_stretch_command(tempo=tempo, sample_rate=sample_rate, ffmpeg=ffmpeg), payload)


class PcmCodec:
    """Injectable bundle so the synthesis stage can be tested without ffmpeg."""

    def __init__(self, *, ffmpeg: str = "ffmpeg") -> None:
        self.ffmpeg = ffmpeg

    def decode(self, audio: bytes, *, sample_rate: int) -> np.ndarray:
        return decode_to_pcm(audio, sample_rate=sample_rate, ffmpeg=self.ffmpeg)

    def stretch(self, samples: np.ndarray, *, tempo: float, sample_rate: int) -> np.ndarray:
        return stretch_pcm(samples, tempo=tempo, sample_rate=sample_rate, ffmpeg=self.ffmpeg)
```

- [ ] **Step 4: Chạy test để xác nhận nó pass**

Run: `.venv/bin/python -m pytest tests/test_dub_decode.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/dubbing/decode.py tests/test_dub_decode.py
git commit -m "feat(dubbing): build ffmpeg commands for pcm decode and stretch"
```

---

### Task 6: Stage `synthesize_speech`

**Files:**
- Modify: `app/workers/runner.py` (thêm `_run_synthesize_speech`, đăng ký trong `execute_command` khoảng dòng 927–953)
- Test: `tests/test_dub_synthesis.py`

**Interfaces:**
- Consumes: `fit_tempo` (T1), `read_slice`/`estimate_f0`/`choose_gender` (T2), `TrackSegment`/`build_track`/`write_wav` (T3), `SpeechSynthesisError` (T4), `PcmCodec` (T5)
- Produces: stage `"synthesize_speech"`; đọc `dependencies["speech_synthesizer"]` và `dependencies["pcm_codec"]`

Config của stage:

```json
{"translated_path": "...", "source_audio_path": "...", "media_path": "...",
 "output_path": "...", "report_path": "...",
 "voice_female": "vi-VN-HoaiMyNeural", "voice_male": "vi-VN-NamMinhNeural",
 "default_gender": "female", "rate": "+0%",
 "sample_rate": 24000, "concurrency": 4, "rushed_tempo": 1.5}
```

- [ ] **Step 1: Viết test hỏng**

Tạo `tests/test_dub_synthesis.py`:

```python
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
    # cau "b" chi co 500ms cho 1000ms giong -> tempo 2.0, vuot nguong 1.5
    assert by_id["b"]["tempo"] == 2.0
    assert by_id["b"]["rushed"] is True
    assert report["rushed_count"] == 1


def test_one_failed_line_leaves_its_window_silent_but_completes(tmp_path):
    root = _project(tmp_path, SEGMENTS)
    events = execute_command(_command(root), dependencies={
        "speech_synthesizer": _FakeSynthesizer(fail_ids={"cau hai"}), "pcm_codec": _FakeCodec(),
    })
    assert events[-1].type is WorkerEventType.COMPLETED
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
```

- [ ] **Step 2: Chạy test để xác nhận nó hỏng**

Run: `.venv/bin/python -m pytest tests/test_dub_synthesis.py -v`
Expected: FAIL — mọi test trả về event FAILED với `unsupported worker stage: synthesize_speech`

- [ ] **Step 3: Viết implementation tối thiểu**

Trong `app/workers/runner.py`, thêm import ở đầu file, ngay sau khối import `app.core.translation`:

```python
from app.core.dubbing.decode import PcmCodec
from app.core.dubbing.protocol import SpeechSynthesisError
from app.core.dubbing.timing import fit_tempo
from app.core.dubbing.track import TrackSegment, build_track, write_wav
from app.core.dubbing.voice import choose_gender, estimate_f0, read_slice
from app.providers.tts.edge import VOICE_FEMALE, VOICE_MALE, EdgeTTSProvider
```

và `from concurrent.futures import ThreadPoolExecutor` vào khối import stdlib.

Thêm hàm sau `_run_translate_events`:

```python
def _run_synthesize_speech(command: WorkerCommand, dependencies: dict[str, Any]) -> tuple[WorkerEvent, ...]:
    config = command.config
    translated_path = _project_path(command, "translated_path")
    source_audio_path = _project_path(command, "source_audio_path")
    media_path = _project_path(command, "media_path")
    output_path = _project_path(command, "output_path")
    report_path = _project_path(command, "report_path")
    sample_rate = int(config.get("sample_rate", 24000))
    concurrency = max(1, int(config.get("concurrency", 4)))
    rushed_tempo = float(config.get("rushed_tempo", 1.5))
    rate = str(config.get("rate") or "+0%")
    voices = {
        "male": str(config.get("voice_male") or VOICE_MALE),
        "female": str(config.get("voice_female") or VOICE_FEMALE),
    }
    default_gender = str(config.get("default_gender") or "female")
    voices["default"] = voices.get(default_gender, voices["female"])

    raw = json.loads(translated_path.read_text(encoding="utf-8"))
    media = json.loads(media_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not isinstance(media, dict):
        raise ValueError("synthesis inputs have invalid JSON shape")
    total_ms = int(media.get("duration_ms", 0))
    if total_ms <= 0:
        raise ValueError("media duration_ms is required for speech synthesis")

    synthesizer = dependencies.get("speech_synthesizer") or EdgeTTSProvider()
    codec = dependencies.get("pcm_codec") or PcmCodec()

    # Pitch is read sequentially: one wav handle, and it costs milliseconds.
    # Only the network calls are worth parallelising.
    planned: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        text = str(item.get("target_text") or "").strip()
        start_ms = int(item.get("start_ms", 0))
        end_ms = int(item.get("end_ms", 0))
        if not text or end_ms <= start_ms:
            continue
        samples, source_rate = read_slice(source_audio_path, start_ms, end_ms)
        f0 = estimate_f0(samples, source_rate)
        gender = choose_gender(f0)
        planned.append({
            "id": str(item.get("id") or f"segment-{index + 1}"),
            "text": text, "start_ms": start_ms, "end_ms": end_ms,
            "f0_hz": round(f0, 1), "gender": gender, "voice": voices[gender],
        })

    def speak(entry: dict[str, Any]) -> dict[str, Any]:
        record = dict(entry)
        try:
            audio = synthesizer.synthesize(entry["text"], voice=entry["voice"], rate=rate)
            natural = codec.decode(audio, sample_rate=sample_rate)
            natural_ms = max(1, int(round(len(natural) * 1000 / sample_rate)))
            window_ms = entry["end_ms"] - entry["start_ms"]
            tempo = fit_tempo(natural_ms, window_ms)
            record["tempo"] = round(tempo, 3)
            record["rushed"] = tempo > rushed_tempo
            record["failed"] = False
            record["samples"] = codec.stretch(natural, tempo=tempo, sample_rate=sample_rate)
        except (SpeechSynthesisError, ValueError, RuntimeError) as exc:
            # A dropped line leaves silence; it must not abort a 40-minute job.
            record["tempo"] = 0.0
            record["rushed"] = False
            record["failed"] = True
            record["error"] = str(exc)
            record["samples"] = None
        return record

    results: list[dict[str, Any]] = []
    if planned:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            results = list(pool.map(speak, planned))

    if planned and all(item["failed"] for item in results):
        raise RuntimeError("speech synthesis failed for every line; check the network connection")

    segments = [
        TrackSegment(start_ms=item["start_ms"], end_ms=item["end_ms"], samples=item["samples"])
        for item in results if item["samples"] is not None
    ]
    track = build_track(segments, total_ms=total_ms, sample_rate=sample_rate)
    write_wav(output_path, track, sample_rate=sample_rate)

    report_segments = [
        {key: item[key] for key in ("id", "voice", "f0_hz", "tempo", "rushed", "failed")}
        for item in results
    ]
    rushed_count = sum(1 for item in report_segments if item["rushed"])
    failed_count = sum(1 for item in report_segments if item["failed"])
    _write_json(report_path, {
        "segments": report_segments,
        "rushed_count": rushed_count,
        "failed_count": failed_count,
    })
    return (
        _event(command, WorkerEventType.STARTED, 0.0, "Speech synthesis started"),
        _event(command, WorkerEventType.COMPLETED, 1.0, "Speech synthesis completed", {
            "output_path": str(output_path), "report_path": str(report_path),
            "count": len(report_segments), "rushed_count": rushed_count, "failed_count": failed_count,
        }),
    )
```

Đăng ký trong `execute_command`, ngay sau dòng `if command.stage == "translate_events":`:

```python
        if command.stage == "synthesize_speech":
            return _run_synthesize_speech(command, deps)
```

- [ ] **Step 4: Chạy test để xác nhận nó pass**

Run: `.venv/bin/python -m pytest tests/test_dub_synthesis.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/workers/runner.py tests/test_dub_synthesis.py
git commit -m "feat(dubbing): add synthesize_speech worker stage"
```

---

### Task 7: Tính vị trí phụ đề dưới dải chữ Trung

**Files:**
- Create: `app/core/rendering/placement.py`
- Test: `tests/test_subtitle_placement.py`

**Interfaces:**
- Consumes: không
- Produces:
  - `SubtitlePlacement(str, Enum)` với `ON_ANCHOR = "on_anchor"`, `BELOW_ANCHOR = "below_anchor"`
  - `Placement` dataclass: `x: int`, `y: int`, `font_size: int`, `alignment: int`, `clamped: bool`
  - `place_below_anchor(anchor, *, line_count, font_size, frame_size, base_font_size=None, gap_ratio=0.45, line_height=1.2, min_font_scale=0.78, bottom_safe_ratio=0.02) -> Placement`
  - Hằng: `ALIGN_TOP_CENTER = 8`, `ALIGN_BOTTOM_CENTER = 2`

- [ ] **Step 1: Viết test hỏng**

Tạo `tests/test_subtitle_placement.py`:

```python
"""Dat phu de Viet ngay duoi dai chu Trung ma khong chong len.

Neo bang \\an8 (dinh-giua) chu khong phai \\an2 (day-giua): toa do y khi do
la DINH khoi chu, nen no khong phu thuoc so dong. Cau 1 dong va cau 2 dong
bat dau o cung do cao, chu moc xuong duoi.
"""
from __future__ import annotations

import pytest

from app.core.rendering.placement import (
    ALIGN_TOP_CENTER,
    Placement,
    SubtitlePlacement,
    place_below_anchor,
)

FRAME = (720, 1280)


def test_text_starts_just_below_the_chinese_band():
    result = place_below_anchor((360, 800), line_count=1, font_size=42, frame_size=FRAME)
    assert result.alignment == ALIGN_TOP_CENTER
    assert result.x == 360
    assert result.y == 800 + round(42 * 0.45)
    assert result.font_size == 42
    assert result.clamped is False


def test_one_line_and_two_line_cues_start_at_the_same_height():
    one = place_below_anchor((360, 800), line_count=1, font_size=42, frame_size=FRAME)
    two = place_below_anchor((360, 800), line_count=2, font_size=42, frame_size=FRAME)
    assert one.y == two.y, "an8 anchors the top, so line count must not move it"


def test_font_shrinks_when_two_lines_do_not_fit_below():
    roomy = place_below_anchor((360, 700), line_count=2, font_size=42, frame_size=FRAME)
    tight = place_below_anchor((360, 1150), line_count=2, font_size=42, frame_size=FRAME)
    assert roomy.font_size == 42
    assert tight.font_size == 35
    assert tight.font_size >= round(42 * 0.78)


def test_gap_comes_from_the_base_size_so_the_top_never_moves():
    """Font size varies per cue; the gap must not, or tops drift between cues."""
    big = place_below_anchor((360, 800), line_count=1, font_size=42,
                             base_font_size=42, frame_size=FRAME)
    small = place_below_anchor((360, 800), line_count=2, font_size=33,
                               base_font_size=42, frame_size=FRAME)
    assert big.y == small.y == 800 + round(42 * 0.45)


def test_base_font_size_defaults_to_the_cue_font_size():
    assert (place_below_anchor((360, 800), line_count=1, font_size=42, frame_size=FRAME).y
            == place_below_anchor((360, 800), line_count=1, font_size=42,
                                  base_font_size=42, frame_size=FRAME).y)


def test_clamped_when_even_the_smallest_font_does_not_fit():
    result = place_below_anchor((360, 1270), line_count=2, font_size=42, frame_size=FRAME)
    assert result.clamped is True
    assert result.y + round(result.font_size * 1.2 * 2) <= FRAME[1]


def test_anchor_is_clamped_into_the_frame():
    result = place_below_anchor((9999, 99999), line_count=1, font_size=42, frame_size=FRAME)
    assert 0 <= result.x <= FRAME[0]
    assert 0 <= result.y <= FRAME[1]


def test_horizontal_position_follows_an_off_centre_source():
    result = place_below_anchor((250, 800), line_count=1, font_size=42, frame_size=FRAME)
    assert result.x == 250


@pytest.mark.parametrize("line_count", [0, -1])
def test_line_count_must_be_positive(line_count):
    with pytest.raises(ValueError):
        place_below_anchor((360, 800), line_count=line_count, font_size=42, frame_size=FRAME)


def test_placement_enum_values_are_stable_config_strings():
    assert SubtitlePlacement("on_anchor") is SubtitlePlacement.ON_ANCHOR
    assert SubtitlePlacement("below_anchor") is SubtitlePlacement.BELOW_ANCHOR


def test_placement_is_hashable_and_frozen():
    result = place_below_anchor((360, 800), line_count=1, font_size=42, frame_size=FRAME)
    assert isinstance(result, Placement)
    with pytest.raises(Exception):
        result.y = 5
```

- [ ] **Step 2: Chạy test để xác nhận nó hỏng**

Run: `.venv/bin/python -m pytest tests/test_subtitle_placement.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.rendering.placement'`

- [ ] **Step 3: Viết implementation tối thiểu**

Tạo `app/core/rendering/placement.py`:

```python
"""Where the translated subtitle sits relative to the burned-in source text."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# ASS numpad alignment: 2 is bottom-centre, 8 is top-centre.
ALIGN_BOTTOM_CENTER = 2
ALIGN_TOP_CENTER = 8


class SubtitlePlacement(str, Enum):
    ON_ANCHOR = "on_anchor"
    BELOW_ANCHOR = "below_anchor"


@dataclass(frozen=True, slots=True)
class Placement:
    x: int
    y: int
    font_size: int
    alignment: int
    clamped: bool = False


def place_below_anchor(
    anchor: tuple[int, int],
    *,
    line_count: int,
    font_size: int,
    frame_size: tuple[int, int],
    base_font_size: int | None = None,
    gap_ratio: float = 0.45,
    line_height: float = 1.2,
    min_font_scale: float = 0.78,
    bottom_safe_ratio: float = 0.02,
) -> Placement:
    """Anchor the top of the translated block just under the source subtitle.

    Using \\an8 makes the returned y the TOP of the text block, so it is
    independent of line count: one-line and two-line cues start at the same
    height and grow downward, away from the Chinese text.

    The gap is measured from base_font_size, not the cue's own size. Layout
    already shrinks long cues to fit the frame width, so deriving the gap
    from the shrunken size would drift the top between cues - the exact
    jitter \\an8 is here to prevent.
    """
    if line_count <= 0:
        raise ValueError("line_count must be positive")
    if font_size <= 0:
        raise ValueError("font_size must be positive")
    width, height = frame_size
    x = min(max(0, int(anchor[0])), width)
    baseline = min(max(0, int(anchor[1])), height)
    top = min(baseline + round((base_font_size or font_size) * gap_ratio), height)
    limit = height - round(height * bottom_safe_ratio)
    floor_size = max(1, round(font_size * min_font_scale))

    for size in range(font_size, floor_size - 1, -1):
        if top + round(size * line_height * line_count) <= limit:
            return Placement(x=x, y=top, font_size=size, alignment=ALIGN_TOP_CENTER)

    block = round(floor_size * line_height * line_count)
    return Placement(x=x, y=min(top, max(0, height - block)),
                     font_size=floor_size, alignment=ALIGN_TOP_CENTER, clamped=True)
```

- [ ] **Step 4: Chạy test để xác nhận nó pass**

Run: `.venv/bin/python -m pytest tests/test_subtitle_placement.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/rendering/placement.py tests/test_subtitle_placement.py
git commit -m "feat(render): compute subtitle position below the source band"
```

---

### Task 8: `write_ass` theo chế độ placement, viền dày hơn

**Files:**
- Modify: `app/core/rendering/ass.py` (hàm `write_ass`)
- Modify: `app/core/rendering/style.py` (mặc định `outline_width`, `shadow`)
- Modify: `tests/test_anchor_render.py` (4 test hiện có)
- Test: `tests/test_ass_below_anchor.py`

**Interfaces:**
- Consumes: `SubtitlePlacement`, `place_below_anchor`, `ALIGN_TOP_CENTER` (T7)
- Produces: `write_ass(path, segments, style, *, frame_size, placement)` — `placement` **bắt buộc, keyword-only, không có mặc định**

- [ ] **Step 1: Viết test hỏng**

Tạo `tests/test_ass_below_anchor.py`:

```python
"""Khong xoa chu Trung nua, nen chu Viet phai nam duoi no."""
from __future__ import annotations

import re
from pathlib import Path

from app.core.rendering.ass import write_ass
from app.core.rendering.placement import SubtitlePlacement
from app.core.rendering.style import SubtitleStyle
from app.models.subtitle import SubtitleSegment


def _segment(text="Lao xuong!", anchor=None):
    return SubtitleSegment(
        id="s1", start_ms=1000, end_ms=2000,
        source_language="zh", source_text="fang si", target_language="vi",
        subtitle_optimized_translation=text, anchor=anchor,
    )


def _events(path):
    return [line for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.startswith("Dialogue:")]


def _pos(event):
    match = re.search(r"\\pos\((\d+),(\d+)\)", event)
    assert match, event
    return int(match.group(1)), int(match.group(2))


def test_below_anchor_emits_top_centre_alignment(tmp_path):
    write_ass(tmp_path / "a.ass", [_segment(anchor=(360, 800))], SubtitleStyle(),
              frame_size=(720, 1280), placement=SubtitlePlacement.BELOW_ANCHOR)
    event = _events(tmp_path / "a.ass")[0]
    assert r"\an8" in event
    _, y = _pos(event)
    assert y > 800, "translated text must start below the source subtitle"


def test_on_anchor_keeps_the_original_overlapping_position(tmp_path):
    write_ass(tmp_path / "b.ass", [_segment(anchor=(360, 905))], SubtitleStyle(),
              frame_size=(720, 1280), placement=SubtitlePlacement.ON_ANCHOR)
    event = _events(tmp_path / "b.ass")[0]
    assert r"\an8" not in event
    assert _pos(event) == (360, 905)


def test_one_and_two_line_cues_share_the_same_top(tmp_path):
    short = _segment(text="Ngan", anchor=(360, 800))
    long_text = _segment(text=" ".join(["motu"] * 30), anchor=(360, 800))
    write_ass(tmp_path / "c.ass", [short, long_text], SubtitleStyle(),
              frame_size=(720, 1280), placement=SubtitlePlacement.BELOW_ANCHOR)
    events = _events(tmp_path / "c.ass")
    assert len(events) == 2
    assert _pos(events[0])[1] == _pos(events[1])[1]


def test_below_anchor_without_any_anchor_falls_back_to_style_margin(tmp_path):
    write_ass(tmp_path / "d.ass", [_segment()], SubtitleStyle(),
              frame_size=(720, 1280), placement=SubtitlePlacement.BELOW_ANCHOR)
    event = _events(tmp_path / "d.ass")[0]
    assert r"\pos(" not in event
    assert r"\an8" not in event


def test_style_defaults_use_a_heavier_outline_for_unerased_video():
    style = SubtitleStyle()
    assert style.outline_width == 2.5
    assert style.shadow == 1.0


def test_style_header_carries_the_heavier_outline(tmp_path):
    write_ass(tmp_path / "e.ass", [_segment(anchor=(360, 800))], SubtitleStyle(),
              frame_size=(720, 1280), placement=SubtitlePlacement.BELOW_ANCHOR)
    content = (tmp_path / "e.ass").read_text(encoding="utf-8")
    style_line = next(line for line in content.splitlines() if line.startswith("Style: Default"))
    assert ",2.5,1.0," in style_line


def test_write_ass_reports_what_it_did_for_diagnostics(tmp_path):
    report = write_ass(tmp_path / "f.ass", [_segment(anchor=(360, 800))], SubtitleStyle(),
                       frame_size=(720, 1280), placement=SubtitlePlacement.BELOW_ANCHOR)
    assert report["placement"] == "below_anchor"
    assert report["anchor"] == [360, 800]
    assert report["frame_size"] == [720, 1280]
    assert report["clamped"] is False
    assert report["min_font_size"] == 42


def test_write_ass_reports_clamping_when_there_is_no_room(tmp_path):
    report = write_ass(tmp_path / "g.ass", [_segment(anchor=(360, 1275))], SubtitleStyle(),
                       frame_size=(720, 1280), placement=SubtitlePlacement.BELOW_ANCHOR)
    assert report["clamped"] is True


def test_write_ass_report_without_an_anchor_says_so(tmp_path):
    report = write_ass(tmp_path / "h.ass", [_segment()], SubtitleStyle(),
                       frame_size=(720, 1280), placement=SubtitlePlacement.BELOW_ANCHOR)
    assert report["anchor"] is None
    assert report["clamped"] is False
```

Sửa `tests/test_anchor_render.py`: thêm import và truyền `placement` vào cả bốn lời gọi.

```python
from app.core.rendering.placement import SubtitlePlacement
```

và mỗi lời gọi `write_ass(...)` trong file đó thêm `, placement=SubtitlePlacement.ON_ANCHOR` vào cuối. Cụ thể bốn dòng:

```python
    write_ass(tmp_path / "a.ass", [seg], SubtitleStyle(), frame_size=(720, 1280), placement=SubtitlePlacement.ON_ANCHOR)
    write_ass(tmp_path / "b.ass", [seg], SubtitleStyle(), frame_size=(720, 1280), placement=SubtitlePlacement.ON_ANCHOR)
    write_ass(tmp_path / "c.ass", [seg], SubtitleStyle(), frame_size=(720, 1280), placement=SubtitlePlacement.ON_ANCHOR)
    write_ass(tmp_path / "d.ass", segments, SubtitleStyle(), frame_size=(720, 1280), placement=SubtitlePlacement.ON_ANCHOR)
```

- [ ] **Step 2: Chạy test để xác nhận nó hỏng**

Run: `.venv/bin/python -m pytest tests/test_ass_below_anchor.py tests/test_anchor_render.py -v`
Expected: FAIL — `ModuleNotFoundError` cho `placement` chưa import được vào `ass.py`, và `write_ass() got an unexpected keyword argument 'placement'`

- [ ] **Step 3: Viết implementation tối thiểu**

Trong `app/core/rendering/style.py`, đổi hai mặc định:

```python
    outline_width: float = 2.5
    shadow: float = 1.0
```

Trong `app/core/rendering/ass.py`, thêm import:

```python
from .placement import SubtitlePlacement, place_below_anchor
```

Đổi chữ ký và thân vòng lặp của `write_ass`. Hàm giờ trả về một **dict tóm tắt** thay vì `Path` — `render_final` cần biết nó đã đặt chữ ở đâu và có phải kẹp không để ghi vào `render-report.json`. Bốn test cũ trong `test_anchor_render.py` không dùng giá trị trả về nên không ảnh hưởng.

```python
def write_ass(
    path: Path,
    segments: Sequence[SubtitleSegment],
    style: SubtitleStyle,
    *,
    frame_size: tuple[int, int],
    placement: SubtitlePlacement,
) -> dict[str, object]:
    width, height = frame_size
    layout = SubtitleLayout()
    events: list[str] = []
    anchors = [segment.anchor for segment in segments if segment.anchor is not None]
    fixed_anchor = None
    if anchors:
        fixed_anchor = (
            min(max(0, round(median(anchor[0] for anchor in anchors))), width),
            min(max(0, round(median(anchor[1] for anchor in anchors))), height),
        )
    clamped = False
    font_sizes: list[int] = []
    for segment in segments:
        text = segment.translated_text.strip()
        if not text:
            continue
        laid_out = layout.layout(text, style, frame_size=frame_size)
        rendered = r"\N".join(_escape_ass(line) for line in laid_out.lines)
        override = f"{{\\fs{laid_out.font_size}}}"
        font_sizes.append(laid_out.font_size)
        if fixed_anchor is not None:
            # A shared median anchor follows the source subtitle region while
            # preventing frame-to-frame OCR jitter from moving translated text.
            if placement is SubtitlePlacement.BELOW_ANCHOR:
                # The Chinese text is still on screen, so anchor the TOP of the
                # block below it with \an8 - that keeps y independent of line
                # count, so one- and two-line cues start at the same height.
                spot = place_below_anchor(
                    fixed_anchor,
                    line_count=len(laid_out.lines),
                    font_size=laid_out.font_size,
                    # The gap must come from the style's size, not the cue's
                    # shrunken one, so every cue shares the same top edge.
                    base_font_size=style.font_size,
                    frame_size=frame_size,
                )
                override = f"{{\\an{spot.alignment}\\pos({spot.x},{spot.y})\\fs{spot.font_size}}}"
                font_sizes[-1] = spot.font_size
                clamped = clamped or spot.clamped
            else:
                cx, cy = fixed_anchor
                override = f"{{\\pos({cx},{cy})\\fs{laid_out.font_size}}}"
        events.append(
            f"Dialogue: 0,{_ass_time(segment.start_ms)},{_ass_time(segment.end_ms)},Default,,0,0,0,,{override}{rendered}"
        )
```

Phần `content = "\n".join([...])` và `path.write_text(...)` phía dưới giữ nguyên. Đổi dòng `return path` cuối hàm thành:

```python
    return {
        "placement": placement.value,
        "anchor": list(fixed_anchor) if fixed_anchor is not None else None,
        "frame_size": [width, height],
        "clamped": clamped,
        "min_font_size": min(font_sizes) if font_sizes else style.font_size,
    }
```

Trong `app/core/rendering/renderer.py`, hàm `export` tạm thời truyền `SubtitlePlacement.ON_ANCHOR` để giữ code chạy được — Task 9 sẽ thay bằng tham số thật:

```python
from .placement import SubtitlePlacement
```

```python
            write_ass(ass_path, segments, style, frame_size=(metadata.width, metadata.height),
                      placement=SubtitlePlacement.ON_ANCHOR)
```

- [ ] **Step 4: Chạy test để xác nhận nó pass**

Run: `.venv/bin/python -m pytest tests/test_ass_below_anchor.py tests/test_anchor_render.py -v`
Expected: PASS — 6 test mới xanh, 4 test cũ vẫn xanh

- [ ] **Step 5: Commit**

```bash
git add app/core/rendering/ass.py app/core/rendering/style.py app/core/rendering/renderer.py \
        tests/test_ass_below_anchor.py tests/test_anchor_render.py
git commit -m "feat(render): place translated subtitles below the source band"
```

---

### Task 9: Filtergraph ducking và `render_final`

**Files:**
- Modify: `app/core/rendering/renderer.py` (thêm `build_filter_complex`, `export` nhận `placement`/`dub_audio_path`/`duck_ratio`)
- Modify: `app/workers/runner.py` (`_run_render_final`)
- Test: `tests/test_render_command.py`

**Interfaces:**
- Consumes: `SubtitlePlacement` (T7)
- Produces:
  - `build_filter_complex(*, ass_path: str, dubbed: bool, duck_ratio: int) -> str`
  - `SubtitleRenderer.export(*, video, segments, style, output_path, srt_path, placement, dub_audio_path=None, duck_ratio=12)` — tham số đầu đổi tên từ `clean_video` thành `video`
  - `RenderResult` thêm trường `placement_report: dict[str, object]`
  - `_run_render_final` đọc config khoá `video_path` (thay `clean_video_path`), `subtitle_placement`, `dub_audio_path`, `duck_ratio`, `report_path`; ghi `cache/exports/render-report.json`

`runner.py:240` là **chỗ gọi `renderer.export` duy nhất** trong toàn repo (`export_service.py` có một hàm `export` khác, không liên quan tới renderer), nên đổi tên tham số không lan ra đâu.

- [ ] **Step 1: Viết test hỏng**

Tạo `tests/test_render_command.py`:

```python
"""Filtergraph tron audio, kiem bang so chuoi chu khong chay ffmpeg.

sidechaincompress la MOT filter duy nhat bat ke bao nhieu cau thoai, thay vi
mot filtergraph khong lo voi vai tram bieu thuc enable='between(t,...)'.
"""
from __future__ import annotations

import pytest

from app.core.rendering.renderer import build_filter_complex


def test_without_dubbing_only_the_subtitle_filter_is_built():
    graph = build_filter_complex(ass_path="/tmp/t.ass", dubbed=False, duck_ratio=12)
    assert graph == ""


def test_dubbed_graph_burns_subtitles_and_ducks_the_original():
    graph = build_filter_complex(ass_path="/tmp/t.ass", dubbed=True, duck_ratio=12)
    assert "[0:v]ass=/tmp/t.ass[v]" in graph
    assert "sidechaincompress=" in graph
    assert "ratio=12" in graph
    assert "amix=inputs=2:duration=first:normalize=0[aout]" in graph


def test_duck_ratio_reaches_the_filter():
    for ratio in (6, 12, 20):
        graph = build_filter_complex(ass_path="/tmp/t.ass", dubbed=True, duck_ratio=ratio)
        assert f"ratio={ratio}" in graph


def test_graph_uses_a_single_sidechain_filter_regardless_of_cue_count():
    graph = build_filter_complex(ass_path="/tmp/t.ass", dubbed=True, duck_ratio=12)
    assert graph.count("sidechaincompress") == 1
    assert "enable=" not in graph


def test_attack_and_release_match_the_narration_feel():
    graph = build_filter_complex(ass_path="/tmp/t.ass", dubbed=True, duck_ratio=12)
    assert "attack=20" in graph
    assert "release=400" in graph


@pytest.mark.parametrize("ratio", [0, -1])
def test_invalid_duck_ratio_is_rejected(ratio):
    with pytest.raises(ValueError):
        build_filter_complex(ass_path="/tmp/t.ass", dubbed=True, duck_ratio=ratio)


def test_render_stage_writes_a_placement_report(tmp_path):
    """Canh bao ve vi tri phu de sinh ra o render_final, sau synthesize_speech,
    nen chung khong the ghi nguoc vao dub-report.json."""
    import json

    from app.core.rendering.renderer import RenderResult
    from app.workers.protocol import WorkerCommand, WorkerEventType
    from app.workers.runner import execute_command

    root = tmp_path / "project"
    (root / "cache" / "translation").mkdir(parents=True)
    (root / "cache" / "translation" / "t.json").write_text(json.dumps([
        {"id": "a", "start_ms": 0, "end_ms": 1000, "target_text": "Chao", "anchor": [360, 800]}
    ]), encoding="utf-8")
    source = root / "source.mp4"
    source.write_bytes(b"")

    class _FakeRenderer:
        def export(self, **kwargs):
            return RenderResult(
                output_path=kwargs["output_path"], srt_path=kwargs["srt_path"],
                placement_report={"placement": "below_anchor", "anchor": [360, 800],
                                  "frame_size": [720, 1280], "clamped": True, "min_font_size": 33},
            )

    command = WorkerCommand("job-1", "render_final", str(root), {
        "video_path": str(source),
        "translated_path": str(root / "cache" / "translation" / "t.json"),
        "output_path": str(root / "exports" / "final_vi.mp4"),
        "srt_path": str(root / "subtitles" / "t.srt"),
        "report_path": str(root / "exports" / "render-report.json"),
        "subtitle_placement": "below_anchor",
    })
    events = execute_command(command, dependencies={"renderer": _FakeRenderer()})
    assert events[-1].type is WorkerEventType.COMPLETED, events[-1].message
    report = json.loads((root / "exports" / "render-report.json").read_text(encoding="utf-8"))
    assert report["placement"] == "below_anchor"
    assert report["clamped"] is True
    assert events[-1].data["clamped"] is True
```

- [ ] **Step 2: Chạy test để xác nhận nó hỏng**

Run: `.venv/bin/python -m pytest tests/test_render_command.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_filter_complex'`

- [ ] **Step 3: Viết implementation tối thiểu**

Trong `app/core/rendering/renderer.py`, thêm hàm ở mức module, ngay sau `class RenderError`:

```python
def build_filter_complex(*, ass_path: str, dubbed: bool, duck_ratio: int) -> str:
    """Filtergraph that burns subtitles and, when dubbing, ducks the original audio.

    Returns "" when there is no dub track: that path keeps the historical
    -vf/-c:a copy command, so a subtitle-only render never re-encodes audio.
    """
    if not dubbed:
        return ""
    if duck_ratio <= 0:
        raise ValueError("duck_ratio must be positive")
    return (
        f"[0:v]ass={ass_path}[v];"
        "[0:a]aresample=48000[orig];"
        "[1:a]aresample=48000[dub];"
        f"[orig][dub]sidechaincompress=threshold=0.02:ratio={duck_ratio}:attack=20:release=400[ducked];"
        "[ducked][dub]amix=inputs=2:duration=first:normalize=0[aout]"
    )
```

Đổi `export` thành:

```python
    def export(
        self,
        *,
        video: str | Path,
        segments: Sequence[SubtitleSegment],
        style: SubtitleStyle,
        output_path: str | Path,
        srt_path: str | Path,
        placement: SubtitlePlacement,
        dub_audio_path: str | Path | None = None,
        duck_ratio: int = 12,
    ) -> RenderResult:
        source = Path(video)
        output = Path(output_path)
        srt = Path(srt_path)
        if not source.is_file():
            raise RenderError(f"render source video does not exist: {source}")
        try:
            metadata = self.media.probe(source)
        except MediaError as exc:
            raise RenderError(str(exc)) from exc
        output.parent.mkdir(parents=True, exist_ok=True)
        write_srt(srt, segments)
        ffmpeg = shutil.which(self.ffmpeg)
        if ffmpeg is None:
            raise RenderError(f"required renderer binary is not installed: {self.ffmpeg}")
        dub = Path(dub_audio_path) if dub_audio_path else None
        dubbed = dub is not None and dub.is_file() and metadata.has_audio
        with tempfile.TemporaryDirectory(prefix="subreplace-render-") as tmp:
            ass_path = Path(tmp) / "target.ass"
            placement_report = write_ass(
                ass_path, segments, style,
                frame_size=(metadata.width, metadata.height), placement=placement,
            )
            escaped = self._escape_filter_path(ass_path)
            command = [ffmpeg, "-y", "-i", str(source)]
            if dubbed:
                command += ["-i", str(dub)]
                command += [
                    "-filter_complex",
                    build_filter_complex(ass_path=escaped, dubbed=True, duck_ratio=duck_ratio),
                    "-map", "[v]", "-map", "[aout]",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                    "-c:a", "aac", "-b:a", "192k",
                ]
            else:
                command += [
                    "-vf", f"ass={escaped}",
                    "-map", "0:v:0", "-map", "0:a?",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                    "-c:a", "copy",
                ]
            command += ["-movflags", "+faststart", str(output)]
            proc = subprocess.run(command, text=True, capture_output=True, check=False)
            if proc.returncode != 0:
                raise RenderError(f"subtitle render failed: {proc.stderr[-3000:]}")
        if not output.is_file() or output.stat().st_size == 0:
            raise RenderError("renderer did not produce a non-empty output video")
        return RenderResult(output_path=output, srt_path=srt, placement_report=placement_report)
```

Thêm trường vào `RenderResult` (ngay dưới `srt_path`):

```python
@dataclass(frozen=True, slots=True)
class RenderResult:
    output_path: Path
    srt_path: Path
    placement_report: dict[str, object] = field(default_factory=dict)
```

và thêm `field` vào import dataclasses ở đầu file: `from dataclasses import dataclass, field`.

Trong `app/workers/runner.py`, đổi phần đầu và phần cuối của `_run_render_final`:

```python
def _run_render_final(command: WorkerCommand, dependencies: dict[str, Any]) -> tuple[WorkerEvent, ...]:
    config = command.config
    video_path = _project_path(command, "video_path")
    translated_path = _project_path(command, "translated_path")
    output_path = _project_path(command, "output_path")
    srt_path = _project_path(command, "srt_path")
    placement = SubtitlePlacement(str(config.get("subtitle_placement") or "below_anchor"))
    dub_audio_path = _project_path(command, "dub_audio_path") if config.get("dub_audio_path") else None
    duck_ratio = int(config.get("duck_ratio", 12))
    report_path = _project_path(command, "report_path") if config.get("report_path") else None
    target_language = str(config.get("target_language") or "vi")
```

(phần dựng `segments` và `style` ở giữa giữ nguyên), rồi thay hai lệnh cuối hàm:

```python
    renderer = dependencies.get("renderer") or SubtitleRenderer()
    result = renderer.export(
        video=video_path, segments=segments, style=style,
        output_path=output_path, srt_path=srt_path,
        placement=placement, dub_audio_path=dub_audio_path, duck_ratio=duck_ratio,
    )
    report = dict(result.placement_report)
    if report_path is not None:
        _write_json(report_path, report)
    return (
        _event(command, WorkerEventType.STARTED, 0.0, "Final render started"),
        _event(command, WorkerEventType.COMPLETED, 1.0, "Final render completed", {
            "output_path": str(result.output_path), "srt_path": str(result.srt_path), **report,
        }),
    )
```

Thêm import vào `runner.py`:

```python
from app.core.rendering.placement import SubtitlePlacement
```

- [ ] **Step 4: Chạy test để xác nhận nó pass**

Run: `.venv/bin/python -m pytest tests/test_render_command.py tests/test_export_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/rendering/renderer.py app/workers/runner.py tests/test_render_command.py
git commit -m "feat(render): duck original audio under the Vietnamese narration"
```

---

### Task 10: Pipeline tuỳ chọn xoá và chèn stage lồng tiếng

**Files:**
- Modify: `app/application/default_workflow.py` (`build_full_commands`)
- Test: `tests/test_workflow_dub.py`

**Interfaces:**
- Consumes: không (chỉ dựng `WorkerCommand`)
- Produces: `build_full_commands(project, *, translation_config, temporal_config=None, has_audio=True, erase_enabled=False, dub_config=None)`

- [ ] **Step 1: Viết test hỏng**

Tạo `tests/test_workflow_dub.py`:

```python
"""Bo xoa chu Trung khoi duong chay mac dinh, chen stage long tieng.

PipelineWorker bo qua stage dua tren ten stage va vi tri trong danh sach,
nen start va retry bat buoc phai sinh ra cung mot day lenh.
"""
from __future__ import annotations

from pathlib import Path

from app.application.default_workflow import build_full_commands
from app.models.project import Project

TRANSLATION = {"translation_provider": "openai"}
DUB = {"voice_female": "vi-VN-HoaiMyNeural", "voice_male": "vi-VN-NamMinhNeural",
       "default_gender": "female", "rate": "+0%", "duck_ratio": 12}


def _project(tmp_path):
    root = tmp_path / "project"
    root.mkdir(parents=True, exist_ok=True)
    source = root / "source.mp4"
    source.write_bytes(b"")
    return Project(id="p1", name="p", root=root, source_path=source, target_language="vi")


def _stages(commands):
    return [command.stage for command in commands]


def _config(commands, stage):
    return next(command.config for command in commands if command.stage == stage)


def test_erase_stage_is_absent_by_default(tmp_path):
    commands = build_full_commands(_project(tmp_path), translation_config=TRANSLATION)
    assert "erase_video" not in _stages(commands)


def test_render_reads_the_source_video_when_erase_is_off(tmp_path):
    project = _project(tmp_path)
    commands = build_full_commands(project, translation_config=TRANSLATION)
    assert _config(commands, "render_final")["video_path"] == str(project.source_path)


def test_render_reads_the_clean_video_when_erase_is_on(tmp_path):
    project = _project(tmp_path)
    commands = build_full_commands(project, translation_config=TRANSLATION, erase_enabled=True)
    assert "erase_video" in _stages(commands)
    assert _config(commands, "render_final")["video_path"].endswith("clean.mkv")


def test_placement_is_derived_from_the_erase_setting(tmp_path):
    project = _project(tmp_path)
    off = build_full_commands(project, translation_config=TRANSLATION)
    on = build_full_commands(project, translation_config=TRANSLATION, erase_enabled=True)
    assert _config(off, "render_final")["subtitle_placement"] == "below_anchor"
    assert _config(on, "render_final")["subtitle_placement"] == "on_anchor"


def test_synthesis_runs_between_translation_and_render(tmp_path):
    commands = build_full_commands(_project(tmp_path), translation_config=TRANSLATION, dub_config=DUB)
    stages = _stages(commands)
    assert stages.index("translate_events") < stages.index("synthesize_speech") < stages.index("render_final")


def test_render_receives_the_dub_track_and_duck_ratio(tmp_path):
    commands = build_full_commands(_project(tmp_path), translation_config=TRANSLATION, dub_config=DUB)
    render = _config(commands, "render_final")
    assert render["dub_audio_path"] == _config(commands, "synthesize_speech")["output_path"]
    assert render["duck_ratio"] == 12


def test_silent_source_skips_dubbing_entirely(tmp_path):
    commands = build_full_commands(
        _project(tmp_path), translation_config=TRANSLATION, dub_config=DUB, has_audio=False
    )
    stages = _stages(commands)
    assert "synthesize_speech" not in stages
    assert "dub_audio_path" not in _config(commands, "render_final")


def test_dubbing_off_leaves_render_without_a_dub_track(tmp_path):
    commands = build_full_commands(_project(tmp_path), translation_config=TRANSLATION)
    assert "dub_audio_path" not in _config(commands, "render_final")


def test_synthesis_config_points_at_existing_cache_artifacts(tmp_path):
    commands = build_full_commands(_project(tmp_path), translation_config=TRANSLATION, dub_config=DUB)
    config = _config(commands, "synthesize_speech")
    assert config["source_audio_path"] == _config(commands, "extract_audio")["output_path"]
    assert config["translated_path"] == _config(commands, "translate_events")["output_path"]
    assert config["media_path"] == _config(commands, "analyze_media")["output_path"]


def test_same_settings_always_produce_the_same_stage_sequence(tmp_path):
    project = _project(tmp_path)
    first = build_full_commands(project, translation_config=TRANSLATION, dub_config=DUB)
    second = build_full_commands(project, translation_config=TRANSLATION, dub_config=DUB)
    assert _stages(first) == _stages(second)
```

- [ ] **Step 2: Chạy test để xác nhận nó hỏng**

Run: `.venv/bin/python -m pytest tests/test_workflow_dub.py -v`
Expected: FAIL — `TypeError: build_full_commands() got an unexpected keyword argument 'erase_enabled'`

- [ ] **Step 3: Viết implementation tối thiểu**

Thay toàn bộ `build_full_commands` trong `app/application/default_workflow.py`:

```python
def build_full_commands(
    project: Project,
    *,
    translation_config: dict[str, object],
    temporal_config: dict[str, object] | None = None,
    has_audio: bool = True,
    erase_enabled: bool = False,
    dub_config: dict[str, object] | None = None,
) -> tuple[WorkerCommand, ...]:
    root = project.root.resolve()
    core = list(build_core_commands(project, has_audio=has_audio))
    media = root / "cache" / "frames" / "media.json"
    classified = root / "cache" / "detection" / "classified.json"
    audio = root / "cache" / "audio" / "source.wav"
    clean = root / "cache" / "clean" / "clean.mkv"
    erase_report = root / "cache" / "clean" / "erase-report.json"
    translated = root / "cache" / "translation" / f"translated_{project.target_language}.json"
    dub_track = root / "cache" / "dub" / f"dub_{project.target_language}.wav"
    dub_report = root / "cache" / "dub" / "dub-report.json"
    final_video = root / "exports" / f"final_{project.target_language}.mp4"
    render_report = root / "exports" / "render-report.json"
    srt = root / "subtitles" / f"target_{project.target_language}.srt"

    if erase_enabled:
        erase_config: dict[str, object] = {
            "video_path": str(project.source_path),
            "classified_path": str(classified),
            "output_path": str(clean),
            "report_path": str(erase_report),
            "chunk_size": 48,
        }
        if temporal_config:
            erase_config.update(temporal_config)
        core.append(WorkerCommand("pending", "erase_video", str(root), erase_config))

    translate_config: dict[str, object] = {
        "classified_path": str(classified),
        "media_path": str(media),
        "output_path": str(translated),
        "target_language": project.target_language,
        **translation_config,
    }
    core.append(WorkerCommand("pending", "translate_events", str(root), translate_config))

    # Dubbing needs the extracted source audio to read speaker pitch, so a
    # silent source turns it off rather than failing the run.
    dubbing = bool(dub_config) and has_audio
    if dubbing:
        core.append(WorkerCommand("pending", "synthesize_speech", str(root), {
            "translated_path": str(translated),
            "source_audio_path": str(audio),
            "media_path": str(media),
            "output_path": str(dub_track),
            "report_path": str(dub_report),
            **dict(dub_config or {}),
        }))

    render_config: dict[str, object] = {
        # The eraser is optional now, so the render reads whichever video is
        # current: the reconstructed plate, or the untouched source.
        "video_path": str(clean if erase_enabled else project.source_path),
        "translated_path": str(translated),
        "output_path": str(final_video),
        "srt_path": str(srt),
        "report_path": str(render_report),
        "target_language": project.target_language,
        # Keeping the Chinese text means the translation must sit below it.
        "subtitle_placement": "on_anchor" if erase_enabled else "below_anchor",
    }
    if dubbing:
        render_config["dub_audio_path"] = str(dub_track)
        render_config["duck_ratio"] = int(dict(dub_config or {}).get("duck_ratio", 12))
    core.append(WorkerCommand("pending", "render_final", str(root), render_config))
    return tuple(core)
```

- [ ] **Step 4: Chạy test để xác nhận nó pass**

Run: `.venv/bin/python -m pytest tests/test_workflow_dub.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/application/default_workflow.py tests/test_workflow_dub.py
git commit -m "feat(workflow): make erasing optional and insert speech synthesis"
```

---

### Task 11: Nối request, session và preflight

**Files:**
- Modify: `app/application/view_model.py` (`ProjectStartRequest`, `_dub_config`, `_runtime_checks`, `start`)
- Modify: `app/application/session.py` (`start_full`, `retry_full`)
- Test: `tests/test_dub_request.py`

**Interfaces:**
- Consumes: `build_full_commands` (T10), `VOICE_FEMALE`/`VOICE_MALE` (T4)
- Produces:
  - `ProjectStartRequest` thêm: `erase_subtitles: bool = False`, `dub_enabled: bool = True`, `dub_voice_female: str = VOICE_FEMALE`, `dub_voice_male: str = VOICE_MALE`, `dub_default_gender: str = "female"`, `dub_rate: str = "+0%"`, `duck_ratio: int = 12`
  - `StudioViewModel._dub_config(request) -> dict[str, object] | None`
  - `StudioSession.start_full(..., erase_enabled: bool = False, dub_config=None)` và `retry_full(...)` cùng chữ ký phần mới

- [ ] **Step 1: Viết test hỏng**

Tạo `tests/test_dub_request.py`:

```python
"""Retry phai dung dung day lenh ma start da dung.

PipelineWorker doi chieu completed_stages theo ten stage va vi tri, nen
neu retry dung tham so khac start thi checkpoint lech va retry chay sai stage.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.application.session import StudioSession
from app.application.view_model import ProjectStartRequest, StudioViewModel
from app.models.project import Project
from app.providers.tts.edge import VOICE_FEMALE, VOICE_MALE


def _request(**overrides):
    base = dict(source_path="/tmp/a.mp4", project_root="/tmp/p", project_name="p")
    base.update(overrides)
    return ProjectStartRequest(**base)


def test_defaults_dub_on_and_erase_off():
    request = _request()
    assert request.dub_enabled is True
    assert request.erase_subtitles is False
    assert request.dub_voice_female == VOICE_FEMALE
    assert request.dub_voice_male == VOICE_MALE
    assert request.dub_default_gender == "female"
    assert request.duck_ratio == 12


def test_dub_config_carries_voices_and_duck_ratio():
    vm = StudioViewModel(require_desktop=False)
    config = vm._dub_config(_request(duck_ratio=20))
    assert config["voice_female"] == VOICE_FEMALE
    assert config["voice_male"] == VOICE_MALE
    assert config["default_gender"] == "female"
    assert config["rate"] == "+0%"
    assert config["duck_ratio"] == 20


def test_dub_config_is_none_when_dubbing_is_off():
    vm = StudioViewModel(require_desktop=False)
    assert vm._dub_config(_request(dub_enabled=False)) is None


def test_dub_config_rejects_a_blank_voice():
    vm = StudioViewModel(require_desktop=False)
    with pytest.raises(ValueError):
        vm._dub_config(_request(dub_voice_female="  "))


def test_dub_config_rejects_an_unknown_default_gender():
    vm = StudioViewModel(require_desktop=False)
    with pytest.raises(ValueError):
        vm._dub_config(_request(dub_default_gender="other"))


def test_edge_tts_is_required_only_when_dubbing():
    missing = StudioViewModel(require_desktop=False, module_probe=lambda name: name != "edge_tts")
    with_dub = missing._runtime_checks(_request(), has_audio=True)
    without_dub = missing._runtime_checks(_request(dub_enabled=False), has_audio=True)
    assert any(check.name == "edge_tts" and check.status.value == "failed" for check in with_dub)
    assert not any(check.name == "edge_tts" for check in without_dub)


class _RecordingWorkflow:
    def __init__(self):
        self.started = None
        self.retried = None

    def start(self, project, commands, *, on_progress=None):
        self.started = [command.stage for command in commands]
        return object()

    def retry(self, project, job_id, commands, *, on_progress=None):
        self.retried = [command.stage for command in commands]
        return object()


def test_retry_builds_the_same_stage_sequence_as_start(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    source = root / "source.mp4"
    source.write_bytes(b"")
    project = Project(id="p1", name="p", root=root, source_path=source, target_language="vi")
    workflow = _RecordingWorkflow()
    session = StudioSession(workflow=workflow)
    dub_config = {"voice_female": VOICE_FEMALE, "voice_male": VOICE_MALE,
                  "default_gender": "female", "rate": "+0%", "duck_ratio": 12}

    session.start_full(project, translation_config={"translation_provider": "openai"},
                       erase_enabled=False, dub_config=dub_config)
    session.retry_full(project, "job-1", translation_config={"translation_provider": "openai"},
                       erase_enabled=False, dub_config=dub_config)

    assert workflow.started == workflow.retried
    assert "synthesize_speech" in workflow.started
    assert "erase_video" not in workflow.started
```

- [ ] **Step 2: Chạy test để xác nhận nó hỏng**

Run: `.venv/bin/python -m pytest tests/test_dub_request.py -v`
Expected: FAIL — `TypeError: ProjectStartRequest.__init__() got an unexpected keyword argument 'dub_enabled'`

- [ ] **Step 3: Viết implementation tối thiểu**

Trong `app/application/view_model.py`, thêm import:

```python
from app.providers.tts.edge import VOICE_FEMALE, VOICE_MALE
```

Thêm bảy trường vào `ProjectStartRequest`, sau `fp16`:

```python
    erase_subtitles: bool = False
    dub_enabled: bool = True
    dub_voice_female: str = VOICE_FEMALE
    dub_voice_male: str = VOICE_MALE
    dub_default_gender: str = "female"
    dub_rate: str = "+0%"
    duck_ratio: int = 12
```

Thêm method vào `StudioViewModel`, ngay sau `_temporal_config`:

```python
    def _dub_config(self, request: ProjectStartRequest) -> dict[str, object] | None:
        if not request.dub_enabled:
            return None
        female = request.dub_voice_female.strip()
        male = request.dub_voice_male.strip()
        if not female or not male:
            raise ValueError("dubbing requires both a female and a male voice id")
        if request.dub_default_gender not in {"female", "male"}:
            raise ValueError("dub_default_gender must be 'female' or 'male'")
        if request.duck_ratio <= 0:
            raise ValueError("duck_ratio must be positive")
        return {
            "voice_female": female,
            "voice_male": male,
            "default_gender": request.dub_default_gender,
            "rate": request.dub_rate.strip() or "+0%",
            "duck_ratio": int(request.duck_ratio),
        }
```

Trong `_runtime_checks`, thêm sau khối `provider`:

```python
        if request.dub_enabled:
            required.append(("edge_tts", "edge-tts is required for Vietnamese dubbing"))
```

Trong `start`, thay ba dòng cuối phần config:

```python
        translation_config = self._translation_config(request)
        # Validating a temporal plugin the user is not going to run would block
        # the common no-erase path for no reason.
        temporal_config = self._temporal_config(request) if request.erase_subtitles else None
        if temporal_config is not None:
            self.temporal_validator(temporal_config)
        dub_config = self._dub_config(request)
```

và lời gọi `start_full`:

```python
        handle = self.session.start_full(
            project,
            translation_config=translation_config,
            temporal_config=temporal_config,
            on_progress=on_progress,
            has_audio=has_audio,
            erase_enabled=request.erase_subtitles,
            dub_config=dub_config,
        )
```

Trong `app/application/session.py`, thêm hai tham số vào **cả hai** hàm `start_full` và `retry_full`:

```python
        erase_enabled: bool = False,
        dub_config: dict[str, object] | None = None,
```

và chuyển xuống trong cả hai lời gọi `build_full_commands`:

```python
        commands = build_full_commands(
            project,
            translation_config=translation_config,
            temporal_config=temporal_config,
            has_audio=has_audio,
            erase_enabled=erase_enabled,
            dub_config=dub_config,
        )
```

- [ ] **Step 4: Chạy test để xác nhận nó pass**

Run: `.venv/bin/python -m pytest tests/test_dub_request.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/application/view_model.py app/application/session.py tests/test_dub_request.py
git commit -m "feat(app): wire dubbing and optional erasing through the session"
```

---

### Task 12: Giao diện

**Files:**
- Modify: `app/ui/project_setup.py` (các ô mới, `_set_advanced_visible`, `_set_erase_visible`)
- Modify: `app/ui/main_window.py` (`_request_from_form`)
- Modify: `app/ui/processing_view.py` (`STAGES`)
- Test: `tests/test_processing_stages.py`

**Interfaces:**
- Consumes: `ProjectStartRequest` (T11), `VOICE_FEMALE`/`VOICE_MALE` (T4)
- Produces: `DUCK_LEVELS: tuple[tuple[str, int], ...]` trong `app/ui/project_setup.py` — `(("Nhẹ", 6), ("Vừa", 12), ("Mạnh", 20))`

PySide6 có thể không cài trong môi trường test (`qt_compat.PYSIDE6_AVAILABLE`), nên test ở task này chỉ chạm phần **không phụ thuộc Qt**: tuple `STAGES` và hằng `DUCK_LEVELS`.

- [ ] **Step 1: Viết test hỏng**

Tạo `tests/test_processing_stages.py`:

```python
"""Thanh tien trinh phai liet ke dung cac stage that su chay."""
from __future__ import annotations

from app.application.default_workflow import build_core_commands
from app.ui.processing_view import STAGES
from app.ui.project_setup import DUCK_LEVELS


def test_synthesis_stage_appears_between_translation_and_render():
    assert STAGES.index("translate_events") < STAGES.index("synthesize_speech") < STAGES.index("render_final")


def test_recovery_stage_is_listed(tmp_path):
    # recover_missing_subtitles da chay trong pipeline nhung thieu trong STAGES,
    # nen tien trinh cua no khong bao gio hien.
    assert "recover_missing_subtitles" in STAGES


def test_every_core_pipeline_stage_has_a_progress_row(tmp_path):
    from app.models.project import Project

    root = tmp_path / "project"
    root.mkdir()
    source = root / "source.mp4"
    source.write_bytes(b"")
    project = Project(id="p", name="p", root=root, source_path=source, target_language="vi")
    for command in build_core_commands(project):
        assert command.stage in STAGES, command.stage


def test_duck_levels_map_labels_to_sidechain_ratios():
    assert DUCK_LEVELS == (("Nhẹ", 6), ("Vừa", 12), ("Mạnh", 20))


def test_default_duck_level_is_the_middle_one():
    assert DUCK_LEVELS[1][1] == 12
```

- [ ] **Step 2: Chạy test để xác nhận nó hỏng**

Run: `.venv/bin/python -m pytest tests/test_processing_stages.py -v`
Expected: FAIL — `ImportError: cannot import name 'DUCK_LEVELS'`, và `ValueError: 'synthesize_speech' is not in tuple`

- [ ] **Step 3: Viết implementation tối thiểu**

Trong `app/ui/processing_view.py`, thay tuple `STAGES`:

```python
STAGES = (
    "analyze_media", "detect_text_events", "ocr_events", "extract_audio", "asr",
    "classify_text_events", "recover_missing_subtitles", "erase_video",
    "translate_events", "synthesize_speech", "render_final",
)
```

Trong `app/ui/project_setup.py`, thêm ở mức module, ngay sau hàm `_natural_video_key`:

```python
DUCK_LEVELS = (("Nhẹ", 6), ("Vừa", 12), ("Mạnh", 20))
```

Thêm import ở đầu file:

```python
from app.providers.tts.edge import VOICE_FEMALE, VOICE_MALE
```

Trong `ProjectSetupView.__init__`, chèn ngay **trước** dòng `self.temporal_provider = QComboBox()`:

```python
            self.dub_enabled = QCheckBox("Lồng tiếng Việt")
            self.dub_enabled.setChecked(True)
            layout.addRow(self.dub_enabled)

            self.dub_voice_female = QComboBox()
            self.dub_voice_female.addItem("Hoài My (nữ)", VOICE_FEMALE)
            layout.addRow("Giọng nữ", self.dub_voice_female)

            self.dub_voice_male = QComboBox()
            self.dub_voice_male.addItem("Nam Minh (nam)", VOICE_MALE)
            layout.addRow("Giọng nam", self.dub_voice_male)

            self.dub_default_gender = QComboBox()
            self.dub_default_gender.addItem("Giọng nữ", "female")
            self.dub_default_gender.addItem("Giọng nam", "male")
            layout.addRow("Giọng khi không xác định được", self.dub_default_gender)

            self.dub_rate = QLineEdit()
            self.dub_rate.setText("+0%")
            layout.addRow("Tốc độ đọc cơ bản", self.dub_rate)

            self.duck_level = QComboBox()
            for label, ratio in DUCK_LEVELS:
                self.duck_level.addItem(label, ratio)
            self.duck_level.setCurrentIndex(1)
            layout.addRow("Giảm tiếng gốc", self.duck_level)

            self.erase_subtitles = QCheckBox("Xoá phụ đề gốc trên hình")
            self.erase_subtitles.setChecked(False)
            self.erase_subtitles.toggled.connect(self._set_erase_visible)
            layout.addRow(self.erase_subtitles)
```

Thêm method sau `_set_advanced_visible`:

```python
        def _set_erase_visible(self, visible: bool) -> None:
            # The temporal plugin fields only mean anything while erasing.
            for widget in (self.temporal_provider, self._repo_row, self._checkpoint_row, self.fp16):
                self._layout.setRowVisible(widget, visible and self.advanced.isChecked())
```

Đổi `_set_advanced_visible` để không bật lại nhóm eraser khi đang tắt xoá:

```python
        def _set_advanced_visible(self, visible: bool) -> None:
            for widget in (self.project_name, self.translation_model, self.endpoint, self.local_command):
                self._layout.setRowVisible(widget, visible)
            self._set_erase_visible(self.erase_subtitles.isChecked())
```

Ở cuối `__init__`, sau `self._set_advanced_visible(False)`, thêm:

```python
            self._set_erase_visible(False)
```

Trong `app/ui/main_window.py`, hàm `_request_from_form`, thêm bảy tham số vào lời gọi `ProjectStartRequest(...)`, ngay sau `fp16=view.fp16.isChecked(),`:

```python
                erase_subtitles=view.erase_subtitles.isChecked(),
                dub_enabled=view.dub_enabled.isChecked(),
                dub_voice_female=str(view.dub_voice_female.currentData()),
                dub_voice_male=str(view.dub_voice_male.currentData()),
                dub_default_gender=str(view.dub_default_gender.currentData()),
                dub_rate=view.dub_rate.text().strip() or "+0%",
                duck_ratio=int(view.duck_level.currentData()),
```

- [ ] **Step 4: Chạy test để xác nhận nó pass**

Run: `.venv/bin/python -m pytest tests/test_processing_stages.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/ui/project_setup.py app/ui/main_window.py app/ui/processing_view.py tests/test_processing_stages.py
git commit -m "feat(ui): add dubbing controls and an optional erase toggle"
```

---

### Task 13: CLI, đóng gói, prompt dịch, tài liệu

**Files:**
- Modify: `app/cli.py`
- Modify: `app/providers/translation/json_contract.py` (`prompt_for_translation`)
- Modify: `pyproject.toml`
- Modify: `installers/install-linux.sh`, `installers/install-windows.ps1`, `run-linux.sh`, `run-windows.ps1`
- Modify: `README.md`
- Test: `tests/test_cli_dub_flags.py`

**Interfaces:**
- Consumes: `ProjectStartRequest` (T11), `VOICE_FEMALE`/`VOICE_MALE` (T4)
- Produces: cờ CLI `--erase-subtitles`, `--no-dub`, `--dub-voice-female`, `--dub-voice-male`, `--dub-default-gender`, `--dub-rate`, `--duck-ratio`

CLI nhận `--duck-ratio` là số nguyên trực tiếp, **không** dùng `DUCK_LEVELS` — bảng nhãn Nhẹ/Vừa/Mạnh chỉ phục vụ giao diện.

- [ ] **Step 1: Viết test hỏng**

Tạo `tests/test_cli_dub_flags.py`:

```python
"""subreplace-batch phai dung duoc tinh nang moi ma khong can UI."""
from __future__ import annotations

import pytest

from app.cli import build_parser
from app.providers.tts.edge import VOICE_FEMALE, VOICE_MALE
from app.providers.translation.json_contract import prompt_for_translation


def _parse(*extra):
    return build_parser().parse_args(["--source", "a.mp4", "--project", "p", *extra])


def test_dubbing_is_on_and_erasing_is_off_by_default():
    args = _parse()
    assert args.no_dub is False
    assert args.erase_subtitles is False
    assert args.dub_voice_female == VOICE_FEMALE
    assert args.dub_voice_male == VOICE_MALE
    assert args.dub_default_gender == "female"
    assert args.duck_ratio == 12


def test_dubbing_can_be_turned_off():
    assert _parse("--no-dub").no_dub is True


def test_erasing_can_be_turned_on():
    assert _parse("--erase-subtitles").erase_subtitles is True


def test_duck_ratio_accepts_the_documented_levels():
    for ratio in (6, 12, 20):
        assert _parse("--duck-ratio", str(ratio)).duck_ratio == ratio


def test_default_gender_is_restricted_to_male_or_female():
    with pytest.raises(SystemExit):
        _parse("--dub-default-gender", "other")


def test_translation_prompt_asks_for_dub_friendly_length():
    prompt = prompt_for_translation([], "vi", {})
    lowered = prompt.lower()
    assert "dub" in lowered or "spoken" in lowered
```

- [ ] **Step 2: Chạy test để xác nhận nó hỏng**

Run: `.venv/bin/python -m pytest tests/test_cli_dub_flags.py -v`
Expected: FAIL — `AttributeError: 'Namespace' object has no attribute 'no_dub'`

- [ ] **Step 3: Viết implementation tối thiểu**

Trong `app/cli.py`, thêm import và bảy `add_argument` sau `--no-fp16`:

```python
from app.providers.tts.edge import VOICE_FEMALE, VOICE_MALE
```

```python
    parser.add_argument("--erase-subtitles", action="store_true")
    parser.add_argument("--no-dub", action="store_true")
    parser.add_argument("--dub-voice-female", default=VOICE_FEMALE)
    parser.add_argument("--dub-voice-male", default=VOICE_MALE)
    parser.add_argument("--dub-default-gender", choices=("female", "male"), default="female")
    parser.add_argument("--dub-rate", default="+0%")
    parser.add_argument("--duck-ratio", type=int, default=12)
```

Trong `main`, thêm vào `ProjectStartRequest(...)` sau `fp16=not args.no_fp16,`:

```python
        erase_subtitles=args.erase_subtitles,
        dub_enabled=not args.no_dub,
        dub_voice_female=args.dub_voice_female,
        dub_voice_male=args.dub_voice_male,
        dub_default_gender=args.dub_default_gender,
        dub_rate=args.dub_rate,
        duck_ratio=args.duck_ratio,
```

Trong `app/providers/translation/json_contract.py`, đổi câu thứ ba của `prompt_for_translation`:

```python
        "natural is a faithful natural translation; optimized is concise subtitle-ready text "
        "that is short enough to be spoken aloud within the original line's duration when dubbed. "
```

Trong `pyproject.toml`, thêm extra sau `cloud`:

```toml
dub = [
  "edge-tts>=7.0",
]
```

Trong bốn file cài đặt, đổi `[desktop,media,ai,cloud]` thành `[desktop,media,ai,cloud,dub]`. Đúng bốn dòng, mỗi file một dòng:

| File | Dòng | Nội dung hiện tại |
|---|---|---|
| `installers/install-linux.sh` | 39 | `"$INSTALL_DIR/.venv/bin/python" -m pip install "$WHEEL[desktop,media,ai,cloud]"` |
| `installers/install-windows.ps1` | 74 | `& $RuntimePython -m pip install "${Wheel}[desktop,media,ai,cloud]"` |
| `run-linux.sh` | 46 | `"$VENV/bin/python" -m pip install -e "$ROOT_DIR[desktop,media,ai,cloud]"` |
| `run-windows.ps1` | 36 | `& $RuntimePython -m pip install -e "${RootDir}[desktop,media,ai,cloud]"` |

Kiểm bằng: `grep -rn "desktop,media,ai,cloud\]" installers/ run-linux.sh run-windows.ps1` — phải không còn kết quả nào.

Trong `README.md`, thêm mục sau phần "Multi-Video Queue":

```markdown
## Vietnamese Dubbing

- Generate Vietnamese narration for every translated line with edge-tts.
- Assign a male or female voice per line from the original speaker's pitch.
- Fit each line to its subtitle window, and flag over-compressed lines in
  `cache/dub/dub-report.json`.
- Duck the original audio under the narration; music and effects stay.
- Requires an internet connection during the synthesis stage.

Erasing the burned-in Chinese subtitles is now off by default. With erasing
off the Vietnamese subtitle is anchored below the Chinese band instead of
over it, and the render skips a full decode/encode pass of every frame.
```

- [ ] **Step 4: Chạy test để xác nhận nó pass**

Run: `.venv/bin/python -m pytest tests/test_cli_dub_flags.py -v`
Expected: PASS

- [ ] **Step 5: Chạy toàn bộ suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS — toàn bộ test cũ và mới đều xanh.

Việc đổi tên `clean_video` → `video` không lan ra test cũ nào: `app/workers/runner.py:240` là chỗ gọi `renderer.export` duy nhất trong repo, và `tests/test_export_service.py` gọi `ExportService().export(...)` — một hàm khác hẳn, không liên quan tới renderer. Nếu suite vẫn đỏ, đó là lỗi thật cần điều tra chứ không phải ripple đã lường trước.

- [ ] **Step 6: Commit**

```bash
git add app/cli.py app/providers/translation/json_contract.py pyproject.toml \
        installers/ run-linux.sh run-windows.ps1 README.md tests/test_cli_dub_flags.py
git commit -m "feat: expose dubbing through the CLI and package the dub extra"
```

---

## Kiểm chứng thủ công (sau Task 13)

Máy không chấm được chất lượng nghe và vị trí chữ trên hình thật. Chạy một clip ngắn thật rồi báo cáo ba thứ:

1. **Vị trí chữ.** Xuất một khung hình có phụ đề: `ffmpeg -ss 00:00:05 -i <output>.mp4 -frames:v 1 frame.png`. Kiểm chữ Việt nằm gọn dưới chữ Trung, không đè, không tràn mép dưới.
2. **Ducking.** Nghe 30 giây có thoại: tiếng Trung có chìm xuống khi giọng Việt nói không, nhạc nền có còn không.
3. **Câu bị nén.** `cat cache/dub/dub-report.json | python -m json.tool | grep -c '"rushed": true'` — báo lại số câu vượt ngưỡng và tổng số câu.

Nếu số câu `rushed` quá cao, cần chỉnh ở hai chỗ (theo thứ tự ưu tiên): prompt dịch cho câu ngắn hơn, hoặc chỉnh tay trong Subtitle Editor.
