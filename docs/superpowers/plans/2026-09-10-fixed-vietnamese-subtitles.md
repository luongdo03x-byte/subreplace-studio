# Fixed Vietnamese Subtitles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Giữ luồng dịch nhiều nguồn và gộp, thêm phụ đề Việt neo trên cố định theo từng nguồn, duyệt preview và chỉ mã hóa hình một lần.

**Architecture:** Module `app/core/subtitle_overlay` sở hữu phân tích, layout, trạng thái SQLite và render contract. Application điều phối hai pha chuẩn bị/duyệt và xuất; UI chỉ gửi yêu cầu và hiển thị trạng thái. Tái sử dụng PaddleTextDetector và FFmpeg, tách chế độ mới khỏi eraser và thuật toán median anchor cũ.

**Tech Stack:** Python >=3.11,<3.14 hiện có; SQLite stdlib, NumPy, PySide6, PaddleOCR, FFmpeg/libass/libx264; pytest. Đo font bằng QFontMetricsF với đúng font đăng ký qua QFontDatabase; render/đo cần QGuiApplication offscreen khi không chạy desktop.

**Spec:** `docs/superpowers/specs/2026-09-10-fixed-vietnamese-subtitles-design.md` (đã được người dùng duyệt trong hội thoại ngày 2026-09-10).

## Global Constraints

### Execution checkpoint — 2026-09-10

Tasks 1–9 have implementation and automated coverage in the isolated `feat/fixed-subtitles` checkout. Orchestration is in `overlay_service.py` and `overlay_batch.py`; metadata is emitted by the service, leaving legacy export intact. End-to-end fixtures live in `test_overlay_batch.py`, `test_overlay_service.py`, and `test_overlay_concat.py` rather than a separate end-to-end file. CLI, desktop review, bundled font, release version and launch instructions are implemented. Original step checkboxes below remain the historical plan, not a claim that every manual check ran.

Task 10 remains partially open: automated suite and wheel packaging are checked separately; the required ten-full-video acceptance and Windows runtime smoke test have not run. A real four-second excerpt generated five previews but exposed conservative detector false positives and slow CPU checking; see `docs/testing/overlay-acceptance.md`. Existing installed app/launcher have not been replaced. Independent review was unavailable, so no independent-review approval is claimed.

- Mỗi video nguồn có một Y riêng, cố định tuyệt đối trong nguồn đó. Y được phép khác khi chuyển nguồn trong video gộp.
- Không xóa, làm mờ, che hoặc crop chữ Trung. Sai khác pixel do mã hóa mất dữ liệu CRF 18–20 được chấp nhận.
- Dò thấy chồng chữ thì chặn nguồn đó, báo timestamp để người dùng chỉnh. Không tự thay Y theo câu, cảnh hoặc khung hình.
- Duyệt preview theo lô. Chỉ gộp khi tất cả nguồn trong danh sách gộp đã được duyệt và render thành công.
- 300 mẫu; lọc 40% đáy, lệch tâm <15%, xuất hiện ≥20%; P95, không max; gap 0.008*h.
- ASS Alignment 8, tối đa hai dòng, kiểm tra `ệ ợ ữ ậ ỗ ằ`; font cố định trong nguồn.
- SQLite lưu revision đã duyệt; thay Y/style/phụ đề/canvas hủy duyệt cũ.
- Không sửa repo `subreplace-studio-next` hoặc bản cài trong giai đoạn viết code. Tạo worktree ở bước thực thi theo skill using-git-worktrees.
- Không làm thêm chức năng TTS. Giữ tích hợp audio hiện có và đưa vào cùng lần encode khi người dùng bật.

## Cách thực thi và xác minh

Thực hiện Task 1–10 theo thứ tự. Mỗi bước test đỏ phải thất bại do hành vi đang thiếu, không phải do môi trường hỏng. Nếu test cũ đã lỗi ở baseline, ghi riêng và chỉ sửa phần liên quan. Chạy từ worktree; dùng `<repo-venv>/bin/python -m pytest` nếu worktree không có `.venv`. Các lệnh dưới giả định `.venv/bin/python` trỏ đúng môi trường dự án.

Không tải model/font từ mạng trong unit tests. Integration cần FFmpeg/libass và font được đóng gói; thiếu dependency là thiếu bằng chứng nghiệm thu, không được báo hoàn thành dựa trên skip. Không gọi API dịch/TTS trong test tự động.

## File map

| Thành phần | File mới | Điểm tích hợp hiện có |
|---|---|---|
| Contract và DB | `app/core/subtitle_overlay/{__init__,models,store}.py` | `app/core/project/service.py` |
| Khung mẫu/dải chữ | `app/core/subtitle_overlay/{sampling,band}.py` | `app/providers/ocr/paddle_detection.py`, `app/core/media/ffmpeg.py` |
| Text/font | `app/core/subtitle_overlay/{captions,typography}.py` | `app/application/subtitle_document.py`, `pyproject.toml` |
| Layout/profile | `app/core/subtitle_overlay/layout.py` | `app/core/rendering/style.py` |
| ASS/PNG/video | `app/core/subtitle_overlay/render.py` | `app/core/rendering/renderer.py` |
| Va chạm | `app/core/subtitle_overlay/collision.py` | detector và frame reader |
| Điều phối | `app/application/overlay_service.py` | `default_workflow.py`, `view_model.py`, `session.py`, `batch.py`, workers |
| Duyệt | `app/ui/overlay_review.py` | `main_window.py`, `project_setup.py` |
| Gộp/export | `app/core/subtitle_overlay/concat.py` | `export_service.py`, `app/cli.py` |

## Task 1: Contract, SQLite và revision bất biến

**Files:** Create `app/core/subtitle_overlay/__init__.py`, `models.py`, `store.py`; modify `app/core/project/service.py`; test `tests/test_overlay_store.py`.

**Interfaces:** Define frozen dataclasses in models.py:

```python
@dataclass(frozen=True)
class Cue:
    id: str
    start_ms: int
    end_ms: int
    text: str

@dataclass(frozen=True)
class LockedLayout:
    y: int
    extra_height: int
    fallback: bool
    measured_frames: int
    warnings: tuple[str, ...] = ()

@dataclass(frozen=True)
class RenderProfile:
    width: int
    height: int
    fps_num: int
    fps_den: int
    audio_mode: str  # copy or aac_stereo

@dataclass(frozen=True)
class DisplayCue:
    source_id: str
    start_ms: int
    end_ms: int
    lines: tuple[str, ...]

@dataclass(frozen=True)
class OverlayStyle:
    font_path: Path
    font_name: str
    font_size: int = 48
    fill: str = '&H00FFFFFF'
    outline_color: str = '&H00000000'
    outline: int = 3
    shadow: int = 2
    margin_x: int = 40
```

`OverlayStore(path: Path)`: `save(source_id: str, payload: dict) -> int`, `load(source_id: str) -> dict`, `approve(source_id: str, revision: int) -> None`, `is_approved(source_id: str, revision: int) -> bool`, `set_state(source_id: str, revision: int, state: str) -> None`. Payload includes JSON-serializable layout/style/profile, input fingerprints, paths, blocking warnings. Store revision and state separately; unchanged payload reuses revision. All mutations compare current revision; stale requests raise ValueError. Store batch membership in `save_batch(batch_id: str, source_ids: tuple[str, ...], profile: dict) -> None` and `load_batch(batch_id: str) -> dict`.

- [ ] Write regression test:

```python
def test_edit_revokes_approval_after_reopen(tmp_path):
    path = tmp_path / 'overlay.sqlite3'
    store = OverlayStore(path)
    first = store.save('a', {'y': 900})
    store.approve('a', first)
    second = store.save('a', {'y': 920})
    reopened = OverlayStore(path)
    assert second > first
    assert not reopened.is_approved('a', second)
    with pytest.raises(ValueError):
        reopened.approve('a', first)
```

- [ ] Run `.venv/bin/python -m pytest tests/test_overlay_store.py -q`; confirm missing module/contract.
- [ ] Implement tables `sources`, `revisions`, `batches`, `batch_items`; parameterized SQL, transactions, `PRAGMA user_version=1`, one connection per operation. Reject revision edits during render, approval when blocking warnings exist. DB under batch/project durable data, never cache; project settings store relative locator, validated against directory traversal.
- [ ] Add reopen, stale revision, idempotent payload, blocked approval, ordered membership tests; run test file until green.
- [ ] Commit only Task 1 files with message `feat: persist overlay revisions and approvals`.

## Task 2: Khung mẫu và P95 dải phụ đề

**Files:** Create `sampling.py`, `band.py`; modify `app/core/media/ffmpeg.py` for rotation/SAR/rational FPS probe; test `tests/test_overlay_band.py`, `tests/test_overlay_sampling.py`.

**Interfaces:** `FrameSample(index: int, timestamp_ms: int, image: np.ndarray)` defined in sampling.py; `sample_frames(video: Path, count: int = 300) -> Iterator[FrameSample]`, `iter_frames(video: Path) -> Iterator[FrameSample]` preserve timestamps and display orientation. `BandResult(bottom: float | None, measured_frames: int, decoded_frames: int, warnings: tuple[str, ...])` in band.py. `detect_band(samples: Iterable[FrameSample], detector: TextDetector, frame_size: tuple[int,int]) -> BandResult`.

- [ ] Add deterministic fake detector test with 100 frames: 95 centered boxes ending at 900, five at 1000, and off-center signs. Assert P95 interpolation returns 905, not 1000; repeated boxes in one frame do not inflate frequency. Crop-origin test must recover full-frame Y.

```python
def test_quantile_not_max():
    values = [900] * 95 + [1000] * 5
    assert float(np.percentile(values, 95, method='linear')) == 905
```

This small arithmetic oracle accompanies `detect_band` tests; it does not replace them.
- [ ] Run both new test files; confirm detector contract missing.
- [ ] Decode streaming via existing available media backend, select nearest actual frame to evenly spaced target timestamps, deduplicate short videos. Never load entire video into memory. Add cancel callback on service layer; errors must reach report.
- [ ] Implement grouping: merge same-line boxes with vertical overlap ≥0.5 and gap ≤0.04W; merge nearby lines with horizontal overlap ≥0.5 and gap ≤1.5 median line height. Cluster blocks whose bottom differs ≤0.04H; count distinct frames. These initial thresholds are detector version `overlay-band-v1`, tune only against labeled fixtures and bump version when changed. Filter block bottom-region/center, retain qualifying clusters, P95 all retained block bottoms. Validate bilingual/two-line blocks before filtering.
- [ ] Add tests for 19%/20% boundary, empty detections, under-300 video, missing frames, bilingual blocks, VFR timestamps, rotation and SAR. Run the new files and `tests/test_paddle_parse_regression.py`.
- [ ] Commit `feat: detect persistent subtitle bands from video samples`.

## Task 3: Font thực và phân đoạn hiển thị

**Files:** Create `captions.py`, `typography.py`; modify `pyproject.toml` for renderer dependency/package data and add `app/assets/fonts/BeVietnamPro-Regular.ttf` plus verified license; tests `tests/test_overlay_captions.py`, `tests/test_overlay_typography.py`.

**Interfaces:** `read_cues(path: Path) -> tuple[Cue,...]`; `FontMetrics(style: OverlayStyle)` with `width(text: str) -> float`, `line_height: int`, `has_glyphs(text: str) -> bool`; `segment_cues(cues: tuple[Cue,...], metrics: FontMetrics, width: int) -> tuple[tuple[DisplayCue,...], tuple[str,...]]`.

- [ ] Write tests using an injected metrics double (width = len(text)*10) to force splitting; assert concatenated words remain identical and timings contiguous inside original interval:

```python
assert ' '.join(word for cue in displayed for line in cue.lines
                for word in line.split()) == original.text
assert all(1 <= len(cue.lines) <= 2 for cue in displayed)
assert displayed[0].start_ms == original.start_ms
assert displayed[-1].end_ms == original.end_ms
```

- [ ] Run `.venv/bin/python -m pytest tests/test_overlay_captions.py tests/test_overlay_typography.py -q`; confirm failure.
- [ ] Implement SRT and ASS text/time parsing, including ASS commas in text, centiseconds and override removal; reject malformed/overlapping intervals. Normalize NFC. Enumerate word splits, minimize max line width then imbalance; split long cues into groups fitting two lines. Allocate integer ms proportionally to character count with last cue ending exactly at original end. Return reading-speed warnings below 800 ms or above 20 chars/s; unbreakable overflow is blocking.
- [ ] Register exact font file through QFontDatabase, set pixel size, disable silent fallback by glyph preflight. Measure ascent/descent/leading plus border/shadow reserve. Run offscreen Qt on main process or dedicated initialized worker, never create a GUI application per cue. Validate bundled font license/provenance with official source before acquisition; package it with wheel.
- [ ] Run tests with `QT_QPA_PLATFORM=offscreen`, test NFC/NFD diacritics and long words. Real libass raster fit is checked in Task 5 because Qt and libass metrics can differ.
- [ ] Commit `feat: lay out Vietnamese captions with verified font metrics`.

## Task 4: Khóa Y/H và profile batch

**Files:** Create `layout.py`; tests `tests/test_overlay_layout.py`.

**Interfaces:** `lock_layout(band: BandResult, frame_size: tuple[int,int], line_height: int, manual_y: int | None = None) -> LockedLayout`; `batch_profile(sources: tuple[tuple[int,int,LockedLayout],...], fps: Fraction, merge: bool) -> RenderProfile`.

- [ ] Add exact oracle:

```python
def test_locked_height_and_manual_override():
    band = BandResult(1000.0, 240, 300, ())
    auto = lock_layout(band, (1920, 1080), 60)
    assert (auto.y, auto.extra_height) == (1009, 71)
    manual = lock_layout(band, (1920, 1080), 60, manual_y=1080)
    assert (manual.y, manual.extra_height) == (1080, 142)
```

- [ ] Run test file to observe failure.
- [ ] Implement ceil(P95+.008H), reserve 2*line_height+ceil(.02H). Manual override replaces auto Y without clamping upward, can require extension; reject negative Y. Fallback .90H landscape/square or .88H portrait. Batch canvas max W and max(H+extension), rounded even; preserve per-source extension in layout. Empty batch/FPS≤0 raise ValueError. Use first-source rational FPS; SAR≠1 preflight blocks new mode.
- [ ] Add tests for canvas larger than source, odd dimensions, fallback flags, two line/one line invariance and extension metadata unaffected by common canvas.
- [ ] Commit `feat: lock source layouts and plan shared render canvas`.

## Task 5: ASS, preview và video cùng đường render

**Files:** Create `render.py`; modify `app/core/rendering/renderer.py` only at explicit new-mode dispatch; tests `tests/test_overlay_render.py`.

**Interfaces:** `write_overlay_ass(path: Path, cues: tuple[DisplayCue,...], style: OverlayStyle, layout: LockedLayout, profile: RenderProfile) -> Path`; `render_preview(video: Path, timestamp_ms: int, ass: Path, profile: RenderProfile, output: Path) -> Path`; `render_video(video: Path, ass: Path, profile: RenderProfile, output: Path, dub_audio: Path | None = None, cancel_event=None) -> Path`. Shared `overlay_filter(ass: Path, profile: RenderProfile) -> str` handles escaping and pad anchor.

- [ ] Test ASS events have no per-cue position/font override, Alignment=8, MarginV locked, PlayRes equals canvas. Use parsed fields rather than searching unrelated `8` text. Render glyph fixtures at 1/2 lines and compare first-line placement masks.
- [ ] Run new test file, confirm missing implementation.
- [ ] Implement shared filter: pad at y=0 with horizontal offset rounded to chroma alignment, ASS using bundled font directory, no eraser/scale. Constrain cue width to source safe width even on wider common canvas. Generate complete standard ASS Format and escape literals. Preserve source timestamps in PNG extraction so correct cue appears; do not reset subtitle time with a seek-to-zero shortcut.
- [ ] Render PNG alpha/text masks to validate real libass bounds before locking final preview revision. If Qt estimate under-reserves glyph height, increase reserved line height before final lock; never silently reflow during full render. Use conservative two-line bounds including diacritics for collision tests.
- [ ] Build argv lists, libx264 CRF18 medium; FPS/profile normalization happens here. AAC stereo/silence for merge profile; audio copy only compatible standalone. Reuse existing dub mixer when enabled with pad+ASS in its video branch. Cancellation terminates child; validate temp video with ffprobe before atomic publication.
- [ ] Run synthetic FFmpeg tests including preserved pre-encode Chinese-region pixels, PNG cue timing, bottom diacritics and silent input. Test output command has one video encoding stage. Run `tests/test_render_command.py` and `tests/test_ass_below_anchor.py` for legacy compatibility.
- [ ] Commit `feat: render locked overlays and matching PNG previews`.

## Task 6: Kiểm tra va chạm toàn nguồn

**Files:** Create `collision.py`; tests `tests/test_overlay_collision.py`.

**Interfaces:** `Collision(timestamp_ms: int, bbox: tuple[int,int,int,int])`, `CollisionReport(collisions: tuple[Collision,...], complete: bool, checked_frames: int)` in collision.py. `check_collisions(frames: Iterable[FrameSample], detector: TextDetector, cues: tuple[DisplayCue,...], layout: LockedLayout, line_height: int, source_width: int, cancel_event=None) -> CollisionReport`.

- [ ] Construct 301-frame fixture where only an unsampled late frame contains a box intersecting the active subtitle region; assert detection and immutable Y:

```python
before = layout
report = check_collisions(frames, detector, cues, layout, 60, 1920)
assert report.collisions[0].timestamp_ms == 12000
assert layout == before
```

- [ ] Run test file and confirm failure.
- [ ] Decode every frame, check at source PTS; compare detected original-text boxes with conservative active Vietnamese block bounds including border/shadow. Do not apply 20% frequency filter here, which would discard the rare collision being checked. Deduplicate contiguous warning spans for UI while retaining first timestamp and evidence. Report incomplete on cancellation, raise on detector/decode error; service persists failure and blocks approval. No cues at time means no overlay collision.
- [ ] Test missed detections are not falsely described as proof of safety, two-line originals, bilingual blocks, no active cue, cancellation and no mutation. Run new test file.
- [ ] Commit `feat: block detected subtitle collisions before export`.

## Task 7: Hai pha batch và worker có thể tiếp tục

**Files:** Create `app/application/overlay_service.py`; modify `app/application/{batch,default_workflow,view_model,session,subtitle_document}.py`, `app/workers/{pipeline_worker,process_worker}.py` as required by existing dispatch; tests `tests/test_overlay_workflow.py`, `tests/test_overlay_batch.py`.

**Interfaces:** `OverlayService(store: OverlayStore)` with injected media/detector/renderer factories; `prepare(source_id: str, video: Path, cues: tuple[Cue,...], style: OverlayStyle) -> int`, `finalize_batch(batch_id: str, source_ids: tuple[str,...]) -> None`, `set_y(source_id: str, y: int) -> int`, `approve(source_id: str, revision: int) -> None`, `render(source_id: str, revision: int, output: Path, cancel_event=None) -> Path`. Prepare persists analysis, finalize fixes common profile and generates collision report/5 previews; approve verifies artifacts complete; render rejects missing/stale approval. Existing translated JSON is converted to Cue using existing segment timing adapter, not a new translation call.

- [ ] Write spy-based tests: prepare whole batch calls no encoder; first-source error does not prevent next-source preview; stale approve cannot render; changed text reuses detection but invalidates preview; retry same revision reuses verified output.

```python
service.prepare('a', video, cues, style)
assert renderer.full_calls == []
with pytest.raises(ValueError):
    service.render('a', 1, output)
```

- [ ] Run new test files; confirm failure.
- [ ] Add explicit new placement mode and optional subtitle path to ProjectStartRequest. New preparation command path stops after translation/overlay preparation; external cues bypass ASR/translation dependencies but still require detector. Keep dubbing state separate from DisplayCue splitting. Dispatch overlay stages to narrow service methods instead of growing monolithic worker logic.
- [ ] Split new batch flow into preparation and resumed export using durable ordered manifest. Do not block worker thread waiting for UI approval. Save fingerprints for source bytes, cue data, font bytes, style, detector version, profile and output; key reuse on all dependencies. Cleanup only large disposable cache after verified export, retaining DB/manifest/preview and subtitle data needed for retry.
- [ ] Wire editor invalidation to SQLite before future export can start. A source mutation during active render is rejected. Add concurrent stale-request test and restart from disk test.
- [ ] Run new tests plus `tests/test_batch.py`, `tests/test_processing_stages.py`, `tests/test_workflow_dub.py`. Legacy skip-failed merge test remains for legacy mode; new mode must instead fail incomplete merge.
- [ ] Commit `feat: prepare and resume reviewed subtitle batches`.

## Task 8: Giao diện duyệt theo lô

**Files:** Create `app/ui/overlay_review.py`; modify `app/ui/{main_window,project_setup}.py`; tests `tests/test_overlay_review.py`, `tests/test_main_window_retry.py`.

**Interfaces:** `OverlayReviewView(QWidget)` emits `approve_requested(str, int)` and `y_changed(str, int)`; `show_sources(rows: list[dict]) -> None` consumes persisted source ID/revision/status, five preview paths/timestamps, fallback flag and warning spans. MainWindow delegates to OverlayService via background worker and marshals results through Qt signals.

- [ ] Offscreen UI test: approve disabled for blocked/missing previews; all five images/timestamps available; edited Y clears approved label; approve-all excludes blocked sources and makes fallback confirmation explicit.

```python
view.show_sources([blocked_row])
assert not view.approve_button.isEnabled()
assert view.warning_list.count() > 0
```

- [ ] Run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_overlay_review.py -q` to confirm failure.
- [ ] Implement list preserving input order, selected-source five PNGs, integer Y input, style controls, warning timestamps, revision badge, approve selected/eligible, and render batch action. Label sample text previews explicitly. Display common canvas and changed aspect ratio. Keep existing multiselect/gen/merge controls and retry entry points; route new mode into review screen.
- [ ] Refresh preview asynchronously; ignore stale result revisions. Disable full-render for unapproved source, not analysis of other sources. Retain cancel/progress/reopen behavior.
- [ ] Run UI test plus `tests/test_main_window_retry.py`; manually smoke-test selecting multiple files without starting external API calls.
- [ ] Commit `feat: review locked subtitle previews in batch UI`.

## Task 9: Gộp stream copy, metadata và CLI

**Files:** Create `app/core/subtitle_overlay/concat.py`; modify `app/application/{batch,export_service}.py`, `app/cli.py`; tests `tests/test_overlay_concat.py`, `tests/test_overlay_export.py`, `tests/test_overlay_cli.py`.

**Interfaces:** `concat_verified(inputs: tuple[Path,...], output: Path, profile: RenderProfile, cancel_event=None) -> Path` probes compatible codec, dimensions, SAR, rational rate/time base, pixel format, audio layout/rate and codec extradata. `export_metadata(layout: LockedLayout, profile: RenderProfile, path: Path) -> Path` in export_service.py emits required Vietnamese keys and supplemental canvas/revision information.

- [ ] Synthetic integration uses two generated clips with distinct colors/tones and different source sizes, rendered through Task 5 into same profile. Assert concat keeps order, duration matches within one output frame/audio packet tolerance, no extra libx264 command. Mismatched profile and incomplete membership must fail before publication.

```python
assert merge_commands[-1][merge_commands[-1].index('-c') + 1] == 'copy'
assert all('libx264' not in command for command in merge_commands)
```

- [ ] Run new files; confirm failure.
- [ ] Implement temp concat manifest with correct path escaping, explicit validated paths, cancellable process, output probe and atomic replace. Do not fall back to old normalizing concat. Preserve requested member order and all-or-nothing completeness; success count alone is insufficient.
- [ ] Export metadata alongside each video without deleting SRT unexpectedly; package SQLite/manifest as durable project artifacts. Add CLI new-mode actions `--overlay-prepare`, `--overlay-approve REVISION`, `--overlay-render` with project identifier using existing parser conventions; prepare never implies approve and current non-overlay flags remain accepted. CLI approval is an explicit user operation bound to revision.
- [ ] Run new tests plus `tests/test_export_service.py`, `tests/test_cli_dub_flags.py`; ensure JSON metadata mode reflects source extension, not common padding.
- [ ] Commit `feat: merge reviewed overlays without video reencoding`.

## Task 10: Nghiệm thu và đóng gói

**Files:** Create `tests/test_overlay_end_to_end.py`, `docs/testing/overlay-acceptance.md`; modify `README.md`, `build-release.sh` only for required packaged assets/dependency checks.

**Interfaces:** End-to-end test drives OverlayService and concat_verified with fake translation/detector for deterministic fixtures; separate real-video acceptance uses installed detector and actual 10-video set.

- [ ] Add failing E2E where two sources need different extensions, first has one/two-line cues and second is silent; verify restart between preview and approval, successful render/gộp, revision invalidation and retry caching. Assert output is not published when collision exists.
- [ ] Run `.venv/bin/python -m pytest tests/test_overlay_end_to_end.py -q`; resolve integration gaps in owning modules without unrelated refactors.
- [ ] Run full relevant suite once: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`; report failures/skips, do not hide missing media integration behind green unit tests. Build wheel with `.venv/bin/python -m build --wheel`; inspect the generated wheel using Python's zipfile module, asserting both assets exist:

```python
from pathlib import Path
from zipfile import ZipFile
wheel = max(Path('dist').glob('subreplace_studio-*.whl'), key=lambda p: p.stat().st_mtime_ns)
with ZipFile(wheel) as archive:
    names = archive.namelist()
    assert 'app/assets/fonts/BeVietnamPro-Regular.ttf' in names
    assert 'app/assets/fonts/OFL.txt' in names
```
- [ ] Create acceptance table columns: video hash, dimensions, duration, source subtitle position, two-line/bilingual, auto Y/H, fallback, manual edit, Y drift, collisions, clipped diacritics, >2 lines, pre-encode original-region differences, runtime, result. Include exact six required glyphs and rare-low-subtitle case. Ten-video automatic-detection score uses pre-manual results and must reach 9/10.
- [ ] Locate user-provided sample set read-only; if absent, report that real-video acceptance remains pending rather than substitute synthetic results. Do not claim ≥85% from fixtures. Record real checker false positives/negatives and processing time.
- [ ] Document new batch review/continue flow, metadata interpretation, aspect-ratio padding, font requirements, fallback and unchanged per-source Y after merge. Record installed launcher target and prepare a concrete package/update command; do not overwrite existing install until deployment scope is confirmed or already authorized by then.
- [ ] Commit `test: verify fixed subtitle batches and release assets` after actual checks pass. Final report separates implemented/tested functionality, real-video acceptance and installation status.

## Self-review coverage

| Spec section | Tasks |
|---|---|
| 1–3 scope, old pipeline and isolation | 1, 7, 8, 9 |
| 4 sampling/P95/fallback/manual lock | 2, 4 |
| 5 font, ASS, segmentation, diacritics | 3, 5 |
| 6 full-source check, five PNGs, approval | 5, 6, 7, 8 |
| 7 common canvas and single encode | 4, 5, 9 |
| 8 persistence/retry/metadata | 1, 7, 9 |
| 9 acceptance | 2–10 |
| 10 deployment boundary | 10 |

No implementation has been performed by writing this plan. Implementation choice: sequential inline execution with checkpoints, or subagent-driven task execution if the user selects it. Both follow dependency order and fresh verification; no parallel edits to shared orchestration files.
