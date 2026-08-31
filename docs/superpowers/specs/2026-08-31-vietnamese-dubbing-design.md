# Lồng tiếng Việt + bỏ xoá phụ đề Trung

Ngày: 2026-08-31
Trạng thái: đã duyệt thiết kế, chưa triển khai
Phạm vi: `/home/dluowng/subreplace-studio` (bản 0.3.2)

## 1. Mục tiêu

Hai thay đổi đi cùng nhau:

1. **Thêm lồng tiếng Việt.** Sinh giọng đọc tiếng Việt cho từng câu thoại đã dịch, tự
   phân giọng nam/nữ theo cao độ giọng gốc, trộn đè lên audio gốc theo kiểu ducking.
2. **Bỏ bước xoá phụ đề Trung khỏi đường chạy mặc định.** Chữ Trung được giữ nguyên
   trên hình; phụ đề Việt đặt **ngay dưới** dải chữ Trung, không chồng lên nhau.

Không mục tiêu: xoá code eraser, thay engine dịch, đổi cách phát hiện/OCR.

## 2. Bối cảnh — vì sao phụ đề đang chồng nhau

`_anchor_from_bbox` (`app/workers/runner.py:257`) trả `(x + w/2, y + h)`, tức tâm ngang
và **đáy** của bbox chữ Trung. `write_ass` (`app/core/rendering/ass.py`) lấy trung vị các
anchor rồi phát `{\pos(cx,cy)}`, trong khi style dùng `Alignment: 2` (đáy-giữa). Đáy khối
chữ Việt vì thế được đặt đúng vào đáy khối chữ Trung — chồng khít. Trước giờ không lộ
vì stage `erase_video` đã xoá chữ Trung trước đó.

Bỏ xoá mà không đổi gì khác thì hai lớp chữ đè lên nhau.

## 3. Quyết định thiết kế đã chốt

| # | Quyết định | Lý do |
|---|---|---|
| 1 | Lồng tiếng là **một stage riêng** `synthesize_speech`, không nhét vào `render_final` | Khớp kiến trúc stage/subprocess/checkpoint sẵn có; TTS phụ thuộc mạng nên phải retry được độc lập với render |
| 2 | Trộn audio kiểu **ducking**, giữ nhạc nền và hiệu ứng | Giữ được nền phim; không cần model tách nhạc (Demucs) |
| 3 | Engine TTS: **edge-tts** | Giọng neural tiếng Việt tự nhiên, miễn phí, không cần API key, gói ~2MB |
| 4 | **Ép vừa khung thời gian tuyệt đối** | Chủ dự án chọn; đồng bộ khít với phụ đề |
| 5 | Phân giọng nam/nữ bằng **phân tích cao độ F0**, không dùng pyannote | Không thêm model, không cần token HuggingFace; pyannote tách người nói chứ không cho biết giới tính |
| 6 | Phụ đề Việt neo bằng **`\an8`** (đỉnh-giữa) khi không xoá | `cy` độc lập với số dòng → câu 1 dòng và 2 dòng bắt đầu cùng độ cao, không nhảy |
| 7 | Code eraser **giữ nguyên**, chỉ tắt mặc định | Không mất tính năng; bật lại bằng một ô tích |
| 8 | `SubtitlePlacement` **suy ra từ** `erase_enabled`, không phải ô chọn riêng | Không thể rơi vào tổ hợp hỏng (tắt xoá mà vẫn đè) |
| 9 | Sinh giọng **song song 4 luồng** | Tập 500 câu: ~3 phút thay vì 8–15 phút |
| 10 | Track lồng tiếng ghi **mono 24kHz** | Khớp đúng đầu ra edge-tts; ~65MB/tập thay vì ~500MB |

### Đánh đổi đã ghi nhận

- **Câu bị đọc nhanh.** Ép vừa tuyệt đối nghĩa là câu tiếng Việt dài trong khung ngắn sẽ
  bị nén tốc độ. Giảm nhẹ bằng: (a) prompt dịch yêu cầu câu ngắn gọn hợp lồng tiếng,
  (b) `dub-report.json` liệt kê câu vượt ngưỡng để sửa tay trong Subtitle Editor.
- **Rate-limit.** 4 luồng song song có thể bị Microsoft giới hạn. Cơ chế retry 3 lần có
  backoff hấp thụ; hệ quả xấu nhất là chậm lại, không phải hỏng job.
- **edge-tts là endpoint không chính thức.** Có thể đổi hoặc bị chặn. `SpeechSynthesizer`
  là Protocol nên thay provider khác sau này chỉ đụng một file.
- **Dung lượng đĩa giảm**, không tăng: bỏ `clean.mkv` (hàng GB) tốn hơn nhiều so với
  track wav 65MB. Ngưỡng 2GiB ở `preflight.py:98` giữ nguyên.

## 4. Pipeline

### Trước

```
analyze_media → detect_text_events → ocr_events → extract_audio → asr
  → classify_text_events → recover_missing_subtitles
  → erase_video → translate_events → render_final
```

### Sau (mặc định: không xoá, có lồng tiếng)

```
analyze_media → detect_text_events → ocr_events → extract_audio → asr
  → classify_text_events → recover_missing_subtitles
  → translate_events → synthesize_speech → render_final
```

`erase_video` chỉ xuất hiện khi bật ô "Xoá phụ đề gốc trên hình".

### `app/application/default_workflow.py`

```python
def build_full_commands(
    project, *, translation_config, temporal_config=None, has_audio=True,
    erase_enabled: bool = False,
    dub_config: dict[str, object] | None = None,
) -> tuple[WorkerCommand, ...]
```

Ba thay đổi trong thân hàm:

1. Chỉ thêm lệnh `erase_video` khi `erase_enabled`.
2. `render_final` đổi khoá config `clean_video_path` → `video_path`:
   - `erase_enabled=True` → `cache/clean/clean.mkv`
   - `erase_enabled=False` → `project.source_path`

   Hợp lệ vì `ProjectService.create` copy video nguồn **vào trong** project root
   (`app/core/project/service.py:42`), nên `_project_path()` — hàm chặn mọi đường dẫn
   nằm ngoài project root — vẫn chấp nhận. Không cần nới lỏng kiểm tra nào.
3. Khi `dub_config is not None` **và** `has_audio`, chèn `synthesize_speech` giữa
   `translate_events` và `render_final`; `render_final` nhận thêm `dub_audio_path`
   và `duck_ratio`.

`render_final` luôn nhận thêm khoá `subtitle_placement`, suy trực tiếp:

```python
"subtitle_placement": "on_anchor" if erase_enabled else "below_anchor"
```

### Thứ tự phụ thuộc

`synthesize_speech` cần `translate_events` (bản dịch) và `extract_audio` (`source.wav`
để đo cao độ). Cả hai đứng trước nó trong danh sách, `PipelineWorker` chạy tuần tự theo
thứ tự danh sách — không cần thêm cơ chế dependency.

## 5. Stage `synthesize_speech`

### Hợp đồng vào/ra

**Vào** (đều đã có sẵn trong cache):

| Đường dẫn | Dùng để |
|---|---|
| `cache/translation/translated_<lang>.json` | `id`, `start_ms`, `end_ms`, `target_text` |
| `cache/audio/source.wav` | đo cao độ F0 giọng gốc (định dạng `pcm_s16le`) |
| `cache/frames/media.json` | `duration_ms` — độ dài track cần dựng |

**Config:**

```json
{
  "translated_path": "...", "source_audio_path": "...", "media_path": "...",
  "output_path": "cache/dub/dub_vi.wav", "report_path": "cache/dub/dub-report.json",
  "voice_female": "vi-VN-HoaiMyNeural", "voice_male": "vi-VN-NamMinhNeural",
  "default_gender": "female", "rate": "+0%",
  "sample_rate": 24000, "concurrency": 4, "rushed_tempo": 1.5
}
```

**Ra:**

- `cache/dub/dub_vi.wav` — PCM mono 24kHz, dài đúng `duration_ms`, im lặng ngoài các câu.
- `cache/dub/dub-report.json`:

```json
{
  "segments": [
    {"id": "event-12", "voice": "vi-VN-NamMinhNeural", "f0_hz": 128.4,
     "tempo": 1.72, "rushed": true, "failed": false}
  ],
  "rushed_count": 14, "failed_count": 0
}
```

Cảnh báo về vị trí phụ đề **không** nằm ở đây — chúng sinh ra ở `render_final`, chạy sau
`synthesize_speech`, nên không ghi ngược vào file này được. Xem §7.

### Module mới

```
app/core/dubbing/protocol.py   # SpeechSynthesizer Protocol
app/core/dubbing/voice.py      # đo F0 → chọn giọng          (hàm thuần)
app/core/dubbing/timing.py     # fit_tempo, atempo_chain      (hàm thuần)
app/core/dubbing/track.py      # ghép đoạn thành track dài    (hàm thuần)
app/providers/tts/edge.py      # EdgeTTSProvider              (chỗ duy nhất chạm mạng)
```

Tách theo đúng kiểu `app/core/translation/` + `app/providers/translation/`: `core/` giữ
luật, `providers/` giữ chỗ gọi ra ngoài. Ba module `voice`/`timing`/`track` không đụng
mạng và không gọi ffmpeg nên test thẳng bằng pytest, không cần mock nặng.

### 5.1 Chọn giọng — `voice.py`

Đọc `source.wav` bằng module `wave` của stdlib + numpy. **Không thêm dependency** —
numpy đã nằm trong `dependencies` gốc của `pyproject.toml`.

Với mỗi câu, cắt lát `[start_ms, end_ms)`:

1. Chia khung 40ms, bước nhảy 20ms.
2. Bỏ khung có RMS dưới ngưỡng im lặng.
3. Tự tương quan, tìm đỉnh trong dải trễ ứng với 70–320Hz.
4. Nhận khung là "có giọng" khi tương quan đỉnh > 0.3.
5. Lấy **trung vị F0** của các khung có giọng.

| F0 trung vị | Giọng |
|---|---|
| < 155 Hz | `voice_male` |
| > 190 Hz | `voice_female` |
| 155–190 Hz, hoặc < 5 khung có giọng | `default_gender` |

Vùng chết 155–190Hz là chỗ giọng nữ trầm và giọng nam cao chồng nhau. Đoán bừa ở đó cho
ra kết quả lật qua lật lại giữa các câu liên tiếp — khó chịu hơn hẳn so với rơi về một
giọng ổn định. F0 đo được vẫn ghi vào report để soi lại.

### 5.2 Sinh giọng — `providers/tts/edge.py`

```python
class SpeechSynthesizer(Protocol):
    def synthesize(self, text: str, *, voice: str, rate: str = "+0%") -> bytes: ...
```

`EdgeTTSProvider` bọc `edge_tts.Communicate(...)` (API async) trong `asyncio.run()`,
trả bytes MP3 24kHz mono, ghi ra `cache/dub/seg-<id>.mp3` (xoá sau khi ghép track).

**Song song:** pool 4 luồng. Mỗi câu độc lập nên không có state chia sẻ.

**Chứa lỗi — quy tắc chốt:**

- Mỗi câu retry **3 lần** có backoff.
- Một câu hỏng hẳn → cửa sổ đó **im lặng**, `failed: true` trong report, pipeline **chạy tiếp**.
- **Toàn bộ** câu hỏng → stage FAILED. Mạng chết thì phải báo, và retry được từ đúng stage này.

Lý do phân biệt: rớt mạng một giây không được phép huỷ 40 phút xử lý; nhưng mạng chết
hẳn mà vẫn ra video câm thì là im lặng sai.

### 5.3 Ép vừa khung — `timing.py`

```python
def fit_tempo(natural_ms: int, window_ms: int) -> float          # = natural / window
def atempo_chain(tempo: float) -> tuple[float, ...]
```

ffmpeg 8.0.1 nhận `atempo` từ 0.5 đến 100 trong một tầng, nhưng vượt 2x trong một lần
thì méo tiếng rõ. `atempo_chain` tách thành `n` tầng, mỗi tầng `tempo^(1/n)`:

| tempo | n | Ví dụ |
|---|---|---|
| `abs(tempo - 1.0) < 1e-3` | 0 — trả về `()`, chỗ gọi bỏ hẳn filter | `1.0` → `()` |
| `0.5 <= tempo <= 2.0` | 1 | `1.8` → `(1.8,)` |
| `tempo > 2.0` | `ceil(log2(tempo))` | `2.33` → `(1.526, 1.526)` |
| `tempo < 0.5` | `ceil(log2(1 / tempo))` | `0.3` → `(0.548, 0.548)` |

**Bất biến:** mọi tầng nằm trong `[0.5, 2.0]`, và tích các tầng bằng đúng tempo yêu cầu.

Ngưỡng `rushed_tempo` mặc định 1.5 — vượt là gắn cờ trong report, **không** giới hạn
tempo (ép vừa tuyệt đối là quyết định đã chốt).

### 5.4 Ghép track — `track.py`

Cấp phát `np.zeros(total_samples, dtype=np.int16)` dài bằng `duration_ms`. Với mỗi câu,
đặt mẫu vào đúng offset `start_ms * sr / 1000`.

Sau `atempo`, độ dài thực tế lệch vài mili-giây so với mục tiêu, nên ở đây **cắt hoặc đệm
tới đúng số mẫu của khung**. Chính bước này biến "ép vừa tuyệt đối" thành đảm bảo thật
chứ không phải xấp xỉ.

Fade 5ms hai đầu mỗi đoạn để không lụp bụp ở biên.

**Guard chồng khung:** nếu khung câu N+1 bắt đầu trước khi khung câu N kết thúc thì cắt
bớt câu N. Lý thuyết `coalesce_dialogue_events` đã gộp nên không xảy ra, nhưng rẻ để chặn.

## 6. Trộn audio — `_run_render_final`

Trộn audio bằng `-filter_complex` **cùng lúc** với `-vf` là chỗ ffmpeg hay báo lỗi, nên
khi bật lồng tiếng gộp tất cả vào một filtergraph:

```
-filter_complex
  "[0:v]ass=<escaped_path>[v];
   [0:a]aresample=48000[orig];
   [1:a]aresample=48000[dub];
   [orig][dub]sidechaincompress=threshold=0.02:ratio=<R>:attack=20:release=400[ducked];
   [ducked][dub]amix=inputs=2:duration=first:normalize=0[aout]"
-map "[v]" -map "[aout]" -c:v libx264 -preset medium -crf 18 -c:a aac -b:a 192k
```

`sidechaincompress` là **một filter duy nhất bất kể bao nhiêu câu thoại** — thay vì dựng
filtergraph khổng lồ với vài trăm biểu thức `enable='between(t,...)'`. Attack 20ms /
release 400ms cho cảm giác "chìm xuống nhanh, nổi lên từ từ" đúng kiểu phim thuyết minh.

`<R>` = `duck_ratio`, ánh xạ từ mức người dùng chọn: Nhẹ = 6, Vừa = 12, Mạnh = 20.

**Khi tắt lồng tiếng, lệnh giữ nguyên như hiện tại** — `-vf ass` + `-c:a copy`, không
re-encode audio. Chỉ nhánh có lồng tiếng mới chuyển audio sang AAC.

Hàm dựng filtergraph được tách thành hàm thuần (giống cách `_escape_filter_path` đang
tách) để test bằng so chuỗi, không phải chạy ffmpeg.

## 7. Vị trí phụ đề

### `app/core/rendering/placement.py` (mới)

```python
class SubtitlePlacement(str, Enum):
    ON_ANCHOR    = "on_anchor"     # đè đúng chỗ cũ — khi CÓ xoá
    BELOW_ANCHOR = "below_anchor"  # ngay dưới dải chữ Trung — khi KHÔNG xoá

@dataclass(frozen=True, slots=True)
class Placement:
    x: int
    y: int
    font_size: int
    alignment: int

def place_below_anchor(
    anchor: tuple[int, int], *, line_count: int, font_size: int,
    frame_size: tuple[int, int],
    gap_ratio: float = 0.45, line_height: float = 1.2,
    min_font_scale: float = 0.78, bottom_safe_ratio: float = 0.02,
) -> Placement
```

### Vì sao `\an8`

Nếu giữ `\an2` (đáy-giữa) rồi tính `cy = đáy_chữ_Trung + gap + chiều_cao_khối`, thì chiều
cao khối phụ thuộc số dòng, và vì `\an2` neo theo đáy nên câu 2 dòng **mọc ngược lên trên**
và đâm vào chữ Trung. Phải bù trừ theo số dòng, dễ sai.

Với `\an8` (đỉnh-giữa), toạ độ `\pos` là **đỉnh** khối chữ:

```
cy = median(đáy bbox chữ Trung) + round(font_size * 0.45)
```

`cy` không phụ thuộc số dòng chút nào. Câu 1 dòng và 2 dòng bắt đầu ở cùng độ cao, chữ
mọc xuống dưới. Mép trên khoá cứng ngay dưới chữ Trung → **không thể chồng**, và không
nhảy lên xuống giữa các câu.

Vẫn giữ cơ chế lấy trung vị anchor (commit `699cfe3`) để chống rung theo frame.
`cx` lấy từ trung vị anchor chứ không phải tâm khung, để bám theo nguồn nếu chữ lệch tâm.

Override phát ra: `{\an8\pos(cx,cy)\fs<font_size>}`.

**Không phải đổi payload của `translate_events`** — `anchor` đã sẵn mang đáy bbox, đúng
thứ cần.

### Luật hết chỗ

Nếu `cy + chiều_cao_khối > height - height * 0.02`:

1. Giảm cỡ chữ dần xuống tới sàn `min_font_scale = 0.78` (đúng ngưỡng `SubtitleLayout`
   đang dùng) cho vừa.
2. Vẫn không vừa → kẹp xuống đáy và ghi cảnh báo.

Chỉ xảy ra khi chữ Trung nằm sát mép dưới khung.

Cảnh báo được `render_final` ghi ra `cache/exports/render-report.json` — theo đúng kiểu
`erase_video` đang ghi `erase-report.json` — và kèm vào `data` của event COMPLETED để
hiện lên UI:

```json
{"placement": "below_anchor", "anchor": [360, 905], "clamped": true,
 "font_size": 33, "frame_size": [720, 1280]}
```

### Chữ ký `write_ass`

`write_ass` nhận thêm tham số `placement: SubtitlePlacement` — **bắt buộc, keyword-only,
không có giá trị mặc định**, để mọi chỗ gọi phải nói rõ ý định.

### Style

`SubtitleStyle` đổi mặc định: `outline_width` 2.0 → **2.5**, `shadow` 0.5 → **1.0**.
Chữ Việt giờ nằm đè lên hình thật chứ không phải nền đã xoá sạch, viền cũ hơi mỏng trên
cảnh sáng hoặc rối.

### Không có anchor

Khi không phát hiện được chữ Trung nào, giữ nguyên hành vi hiện tại: dùng `MarginV` của
style, không phát `\pos`.

## 8. UI & cấu hình

### `app/ui/project_setup.py`

Thêm dưới nhóm dịch thuật:

| Điều khiển | Mặc định |
|---|---|
| ☐ `erase_subtitles` — "Xoá phụ đề gốc trên hình" | **tắt** |
| ☑ `dub_enabled` — "Lồng tiếng Việt" | **bật** |
| `dub_voice_female` — combo giọng nữ | `vi-VN-HoaiMyNeural` |
| `dub_voice_male` — combo giọng nam | `vi-VN-NamMinhNeural` |
| `dub_default_gender` — "Giọng khi không xác định được" | nữ |
| `dub_rate` — "Tốc độ đọc cơ bản" | `+0%` |
| `duck_level` — "Giảm tiếng gốc": Nhẹ / Vừa / Mạnh | Vừa |

`duck_level` là combo ba mức chứ không phải ô nhập dB, vì `sidechaincompress` không nhận
dB trực tiếp — bịa ra ô "dB" rồi quy đổi ngầm thì con số hiển thị không đúng với thứ
thực sự xảy ra.

`erase_subtitles` khi tắt sẽ **ẩn** nhóm `temporal_provider` / `temporal_repo_dir` /
`temporal_checkpoint` / `fp16` — chúng chỉ có nghĩa khi xoá. Dùng đúng cơ chế ẩn/hiện
mà ô `advanced` đang dùng sẵn.

### `app/application/view_model.py`

`ProjectStartRequest` thêm bảy trường tương ứng. Thêm hàm dựng config song song với
`_translation_config` và `_temporal_config`:

```python
def _dub_config(self, request) -> dict[str, object] | None:
    # trả None khi tắt lồng tiếng; validate voice id không rỗng
```

Trong `start()`: `_temporal_config` chỉ được gọi (và `temporal_validator` chỉ chạy) khi
`erase_subtitles` bật. Hiện tại nó luôn chạy — validate ProPainter khi người dùng chẳng
xoá gì thì vô nghĩa và có thể chặn nhầm.

### `app/application/session.py` — yêu cầu về tính đúng đắn

`start_full` và `retry_full` đều thêm `erase_enabled` + `dub_config`, chuyển thẳng xuống
`build_full_commands`.

`PipelineWorker` bỏ qua stage dựa trên tập `completed_stages` đối chiếu theo tên stage và
vị trí trong danh sách. Nếu `retry_full` dựng danh sách lệnh khác `start_full` (ví dụ lần
chạy đầu bật lồng tiếng, lần retry lại tắt), checkpoint sẽ lệch và retry chạy sai stage.
**Hai hàm bắt buộc nhận cùng bộ tham số**, và có test khoá chuyện này.

`main_window` đã giữ `self._last_request` để retry — chỉ cần bảo đảm các trường mới đi
cùng nó.

### Các chỗ còn lại

- **`app/core/preflight.py`**: thêm kiểm tra module `edge_tts` vào `_runtime_checks`, chỉ
  khi bật lồng tiếng — giống cách `openai` / `google.genai` đang được thêm theo provider dịch.
- **`app/ui/processing_view.py`**: thêm `synthesize_speech` vào tuple `STAGES`. Nhân tiện
  bổ sung `recover_missing_subtitles` — stage này đang chạy trong pipeline
  (`build_core_commands`) nhưng thiếu trong `STAGES` nên tiến trình của nó không hiện.
- **`pyproject.toml`**: extra mới `dub = ["edge-tts>=7.0"]`; thêm vào danh sách cài trong
  `installers/install-linux.sh`, `installers/install-windows.ps1`, `run-linux.sh`,
  `run-windows.ps1`.
- **`app/cli.py`**: thêm `--erase-subtitles`, `--dub` / `--no-dub`, `--dub-voice-female`,
  `--dub-voice-male`, `--dub-default-gender`, `--duck-level`.
- **Prompt dịch**: bổ sung yêu cầu câu tiếng Việt ngắn gọn, hợp lồng tiếng — giảm số câu
  bị `rushed` ngay từ gốc.
- **Model Manager**: không đụng. edge-tts chạy online, không có model để tải.

## 9. Test

Nguyên tắc: **không test nào chạm mạng, không test nào chạy ffmpeg.** Luật nằm trong hàm
thuần; phần chạm ngoài nằm sau Protocol và được tiêm giả qua cơ chế `dependencies` mà
`runner.py` đã dùng sẵn cho `ocr_engine`, `whisper_model`, `translation_provider`,
`renderer`, `eraser`.

| File | Nội dung |
|---|---|
| `tests/test_dub_timing.py` | `atempo_chain`: mọi tầng trong `[0.5, 2.0]`, tích bằng đúng tempo. Ca `1.0` → `()`, `1.8` → 1 tầng, `2.33` → 2 tầng, `0.3` → 2 tầng, `5.0` → 3 tầng |
| `tests/test_dub_voice.py` | Sóng sin dựng bằng numpy: 120Hz → nam, 220Hz → nữ, 170Hz → mặc định (vùng chết), im lặng và nhiễu trắng → mặc định |
| `tests/test_dub_track.py` | Đoạn dài hơn khung bị cắt còn **đúng** số mẫu; ngắn hơn thì đệm; tổng độ dài bằng `duration_ms`; khoảng trống toàn số 0; khung chồng nhau thì câu trước bị cắt |
| `tests/test_subtitle_placement.py` | `below_anchor` phát `\an8`; `y == anchor_y + gap`; **`y` của câu 1 dòng bằng `y` của câu 2 dòng**; hết chỗ thì thu nhỏ chữ; chạm sàn thì kẹp + cảnh báo |
| `tests/test_workflow_dub.py` | `erase_enabled=False` → không có `erase_video`, `video_path` là source; `True` thì ngược lại. `synthesize_speech` đúng vị trí. `has_audio=False` → không có `synthesize_speech`. `subtitle_placement` suy đúng. **`start_full` và `retry_full` sinh dãy tên stage giống hệt nhau** |
| `tests/test_dub_synthesis.py` | Synthesizer giả. Hỏng câu thứ 3 → khoảng đó im lặng, report ghi nhận, câu khác nguyên vẹn, **stage vẫn COMPLETED**. Hỏng toàn bộ → FAILED |
| `tests/test_render_command.py` | So chuỗi filtergraph: có lồng tiếng thì dùng `-filter_complex` gộp `ass` + `sidechaincompress`, `ratio` khớp mức duck; không lồng tiếng thì lệnh **y hệt hiện tại** |
| `tests/test_anchor_render.py` | Sửa: 4 test hiện có thêm `SubtitlePlacement.ON_ANCHOR`, giữ nguyên giá trị mong đợi. Thành lưới an toàn cho nhánh có-xoá |

## 10. Bảng xử lý lỗi

| Tình huống | Hành vi |
|---|---|
| edge-tts hỏng 1 câu (sau 3 lần retry) | khoảng đó im lặng, ghi report, chạy tiếp |
| edge-tts hỏng **toàn bộ** câu | stage FAILED, retry được từ đúng stage này |
| chưa cài `edge_tts` | preflight chặn trước khi tạo project |
| video không có audio | tự tắt lồng tiếng + `WorkerEventType.LOG` cảnh báo, phụ đề vẫn chạy |
| không nhận được chữ Trung nào | về hành vi cũ: `MarginV` đáy khung, không `\pos` |
| chữ Trung sát đáy khung | thu nhỏ chữ; hết cỡ thì kẹp + ghi `placement_warnings` |
| tempo vượt `rushed_tempo` | vẫn ép đúng khung, gắn cờ `rushed` trong report |

## 11. Kiểm chứng thủ công

Máy không chấm được chất lượng nghe và vị trí chữ trên hình thật. Sau khi triển khai,
chạy một clip ngắn thật và báo cáo ba thứ:

1. Ảnh chụp khung hình — chữ Việt có nằm gọn dưới chữ Trung, không chồng.
2. Một đoạn để nghe thử ducking.
3. Số câu `rushed` trong `dub-report.json`.
