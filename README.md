# SubReplace Studio 0.4.0

The integrated application includes the Next library and publishing workspace. Launch it with `subreplace-studio` or the `subreplace-studio-next` alias. Both use
the `SUBREPLACE_NEXT_APP_DATA` override, `~/.local/share/subreplace-studio-next` on Linux, and a
separate operating-system keyring namespace from older releases. Existing projects and API keys remain in their previous locations.

The first Next phase adds a persistent SQLite Series/Episode library, filename-based episode parsing,
missing/duplicate sequence diagnostics, final-video registration, YouTube desktop OAuth, resumable
uploads, private scheduling, remote IDs, publication state, and an append-only audit trail.

SubReplace Studio is a local Windows/Linux desktop pipeline for translating videos. The default desktop mode retains the original Chinese subtitles and places Vietnamese subtitles below them at a locked position for each source video.

**Eraser rule:** no black rectangles, blur boxes, crop/zoom tricks, or translated text drawn over unerased Chinese. Low-confidence reconstruction is routed to review or an installed temporal inpainting provider.

## Clone And Run

The first run creates a local `.venv` and installs all application dependencies. Git, Python 3.11-3.13, FFmpeg, and FFprobe must already be available.

Linux:

```bash
git clone https://github.com/luongdo03x-byte/subreplace-studio.git
cd subreplace-studio
chmod +x run-linux.sh
./run-linux.sh
```

Windows PowerShell:

```powershell
git clone https://github.com/luongdo03x-byte/subreplace-studio.git
cd subreplace-studio
Set-ExecutionPolicy -Scope Process Bypass
.\run-windows.ps1
```

For a new Windows machine, extract the Windows release ZIP and double-click
`INSTALL-WINDOWS.cmd`. The bootstrap installs Python 3.12 and FFmpeg through
`winget` when needed, installs the complete desktop/AI runtime, and creates a
`SubReplace Studio` desktop shortcut. Internet access is required on first install.

Later launches only require `./run-linux.sh` or `.\run-windows.ps1`. PaddleOCR and Whisper models are downloaded on demand during the first processing job.

## Multi-Video Queue

- Select and reorder up to 10 videos.
- Process videos strictly one at a time to keep memory and GPU usage bounded.
- Produce one translated MP4 for every successful source.
- Optionally create one long MP4 in the selected order.
- In fixed-overlay mode, approve five preview images per source before export.
- Plan a common padded canvas before preview, normalize FPS/audio during the first render, then concatenate with stream copy. No second video encoding pass.
- Keep source images at the top, without scaling/cropping. Non-square-pixel sources require conversion outside this mode and are rejected at preflight.
- Require every source in the selected batch to succeed before merging; retain durable state for retry.
- Sort numeric filenames naturally, for example `1.mp4`, `2.mp4`, `10.mp4`.
- Do not create matching SRT sidecars automatically, preventing duplicate subtitles in VLC.

## Fixed Vietnamese Subtitles (Phase 1)

Keep **Phụ đề Việt xếp dưới — khóa vị trí và duyệt trước khi xuất** enabled in Project.
Select/reorder videos and optionally enable merging as before. Leave **Phụ đề Việt có sẵn** empty to use the existing translation pipeline; alternatively enter an SRT/ASS file, or a directory containing subtitle files matching each video basename. Imported subtitles use the subtitle-only path in this phase.

The app samples up to 300 distinct frames, detects persistent centered subtitle blocks in the bottom 40%, and locks the P95 lower boundary plus 0.8% source height. Insufficient room adds bottom padding. Each source retains its own Y, including inside the merged output.

To reuse placement for later videos with the same composition, set Y in the review screen and click **Lưu Y cho video sau**. The app persists Y as a proportion of source height and skips placement sampling/detection for newly prepared sources. Five previews and approval remain available. **Dò Y tự động cho video sau** removes this default. Previously prepared sources retain their own positions. This skips placement detection only; OCR/ASR needed to translate a new video still runs.

In **Duyệt phụ đề Việt**, inspect five timestamped PNGs, adjust Y/style as needed, then approve individual sources or eligible sources together. Fallback positions require an explicit checkbox confirmation. Edits invalidate previous approval. Placement is computed once from up to 300 distinct sampled frames per source and cached in SQLite. There is no second full-frame text-detection pass; Y/style edits only regenerate previews using the cached band. Sampling still decodes the video and can take time, but text inference is limited to the samples. Rare changes in original subtitle position are not automatically checked: review the previews and use sources whose subtitle band stays fixed.

After updating, stop any old running job and restart the app using `run-phase1-linux.sh`. Reopen the saved batch and choose **Chuẩn bị lại / Retry**. Older batches are migrated to spoken-sentence timing: existing OCR/ASR and band data are retained, while translation and dubbing are regenerated once. The old translation is backed up as `translated_vi.before-speech-timing.json`. Translation credentials and network access are needed for regeneration. New previews require approval again.

For sources with audio, captions follow the original ASR sentence intervals; corroborating OCR helps correct source text without replacing a complete spoken sentence with a fragment. Translation receives each sentence's duration. Dubbing retains natural speed where possible, borrows up to one second of the following pause, and never accelerates beyond 2×. It retries overly long lines with a shorter translation; captions use the exact revised spoken text and timing. A line that still cannot fit is marked failed and left silent; preparation fails if every line fails. ASR text and timing still need review where recognition is inaccurate.

Use **Lồng tiếng Việt (giảm giọng gốc khi đọc)** and **Áp dụng lồng tiếng và chuẩn bị lại** in the review screen to change a saved source. Enabled dubbing overlays Vietnamese speech and ducks the original audio while speaking; disabled dubbing keeps original audio and Vietnamese captions. Imported subtitle files remain subtitle-only.

**Mở lại lô** opens the durable `batch.json` under the output directory's `.subreplace-batches/<batch-id>/`. Keep its adjacent SQLite database and artifacts together. Retry retains source-specific style/Y and verified completed outputs. The legacy mode retains its historical erase/retry/merge behavior when explicitly selected.

Outputs include `*.overlay.json` with locked Y, source extension, fallback flag, measured sample count, warnings, canvas and output fingerprint. Padding added for batch normalization is distinct from the per-source subtitle extension. CRF 18 is lossy: original text pixels are preserved by compositing, not guaranteed bit-identical after compression.

Be Vietnam Pro Regular is bundled under SIL OFL 1.1; custom fonts must contain the Vietnamese glyphs. Display cues are independent of narration cues, limited to two lines, with long text split without dropping words. Reading-speed warnings do not silently rewrite translations.

Headless review of an imported subtitle:

```bash
subreplace-batch --overlay-manifest /output/batch.json --overlay-prepare \
  --source /input/video.mp4 --project /output/project --subtitle /input/vi.srt \
  --output /output/vi.mp4 --no-dub
# Inspect the five PNGs and the printed revision before approval.
subreplace-batch --overlay-manifest /output/batch.json --overlay-approve 3
subreplace-batch --overlay-manifest /output/batch.json --overlay-render
```

Use the actual printed revision, not the example `3`. Add `--accept-fallback` only after inspecting a reported fallback. `--overlay-y 1050` changes Y and regenerates preview. A manifest without an action lists its sources/revisions. See [acceptance checklist](docs/testing/overlay-acceptance.md).

## Vietnamese Dubbing

- Generate Vietnamese narration for every translated line with edge-tts.
- Assign a male or female voice per line from the original speaker's pitch.
- Fit each line to its subtitle window, and flag over-compressed lines in
  `cache/dub/dub-report.json`.
- Duck the original audio under the narration; music and effects stay.
- Requires an internet connection during the synthesis stage.

Erasing the burned-in Chinese subtitles is now off by default. With erasing
off the Vietnamese subtitle is anchored below the Chinese band instead of
over it, and turning erasing off skips the erase stage's full
decode/reconstruct/encode pass over every frame. The render itself always
re-encodes the video (`-crf 18`).

## Workflow

`source video -> media probe -> text events -> PaddleOCR -> optional Whisper ASR -> dialogue/watermark classification -> protected erase -> translation -> FFmpeg/libass render -> export`

The desktop application includes event-based OCR, isolated subprocess workers, durable jobs with retry/cancellation, ProPainter/E2FGVI plugin validation, subtitle editing, synchronized preview, diagnostics, and portable project packages.

## Requirements

- Windows 10/11 64-bit or a current 64-bit Linux distribution.
- Python 3.11-3.13. Python 3.12 is recommended.
- FFmpeg and FFprobe on `PATH`.
- At least 8 GB RAM and 5 GB free disk space.
- Internet access for initial dependency/model downloads.
- An OpenAI or Gemini API key, compatible custom endpoint, or local translation command.

CUDA is optional. The classical eraser and CPU OCR path work without an NVIDIA GPU.

## Release Installers

Extract the release ZIP before running its installer.

Linux:

```bash
chmod +x install-linux.sh
./install-linux.sh
```

Windows PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install-windows.ps1
```

Launch the desktop UI with `subreplace-studio`, or use `subreplace-batch --help` for single-video automation.

## Development

```bash
python -m pip install -e '.[dev,desktop,media,ai,cloud]'
python -m pytest -q
```

API keys can be stored through the operating-system keyring and are not written to project files. Models, project caches, videos, virtual environments, and release artifacts are excluded from Git.

Version 0.4.0 adds reviewed, fixed-position Vietnamese overlays while retaining the multi-video translation and merge workflow.
