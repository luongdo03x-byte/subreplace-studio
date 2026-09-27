# Fixed-overlay validation — 0.4.0

## Approved sampling-only change — 2026-09-10

The user confirmed that subtitle position is fixed in their sources and approved removing the second, full-frame collision-detection pass. Current flow: up to 300 distinct samples → persist band and locked Y → five PNGs → explicit approval → render/merge. Y/style edits reuse the stored band without inference. The preview policy marker forces legacy previews (including collision-blocked ones) to regenerate on preparation/retry without overwriting the source or translation. Historical collision-check observations below describe the previous implementation, not a current release guarantee. Rare subtitle-position changes outside the sampled frames are no longer automatically checked. Sampling still decodes frames; this change removes the additional full-frame inference cost, not all video I/O.

Verification after this change: 264 tests passed, one optional ccache warning, in 28.27 seconds. Both new regression tests failed before implementation: preview attempted a second detector pass, and legacy collision-blocked previews were reused. Both pass after the change. Wheel rebuilt successfully. No running user job was interrupted or automatically approved.

## Automated evidence

Latest verification on 2026-09-10: **262 passed**, one optional Paddle ccache warning, 14.70 seconds. Wheel `subreplace_studio-0.4.0-py3-none-any.whl` built successfully; required font/license and new service/UI modules were verified inside it. Shell syntax checks and `git diff --check` passed. The rotation integration fixture uses FFmpeg's explicit display-rotation option because this machine's FFmpeg did not persist the older `rotate` metadata command.

Run from the checkout using its Python environment:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q
python -m build --wheel --no-isolation
```

On the development machine, Qt multimedia initialization hangs inside the restricted sandbox; running the UI tests outside that sandbox succeeds. This is recorded separately from application test failures. CPU Paddle emits an optional ccache warning; the inference smoke test does not require ccache.

New tests cover persisted revision/approval, interrupted-render recovery, Windows non-terminating process checks, P95 and frequency filtering, two-line blocks, exact layout arithmetic, fallback, SRT/ASS import, balanced wrapping without text loss, bundled glyph coverage, real FFmpeg PNG/video generation, detailed original-region pixel equality before encoding, rare collisions, edits invalidating approval, batch restart/style preservation, reviewed batch export/concat, CLI and desktop batch routing.

Synthetic fixtures use real FFmpeg/libass and font rendering. Only text detection is substituted in deterministic service/batch tests. A separate real Paddle smoke run uses the already cached model. These are not evidence of a 9/10 real-video detection rate.

## Real-input preview smoke test

Source: four-second excerpt beginning at 2 seconds of existing project `03-38`, saved separately under `/home/dluowng/Videos/SubReplace-Phase1-QA/`. Original project files remain unchanged. The two Vietnamese test cues are aligned for this excerpt. Run preparation only, producing a database and five PNG previews; do not approve or full-render a user's source on their behalf.

The excerpt has fewer than 300 distinct frames, so the metadata must record the actual sample count and warn about fewer samples. This smoke test verifies installed model/API compatibility and preview rendering on actual hard-subtitled footage, not whole-video placement accuracy.

Observed result on 2026-09-10: 120 distinct frames decoded, 97 measured frames, P95 bottom 729, locked Y 738, no extension, no fallback. All five PNGs were produced. The frame at 2.2 seconds visibly places Vietnamese below Chinese. Full-frame checking flagged eight frames and correctly withheld approval/export. At least the 0.4-second detection box `(318, 559, 177, 424)` covers clothing decoration rather than a subtitle: this is a detector false positive, not evidence of an actual subtitle overlap. The conservative checker currently requires manual correction/review; do not disable its blocking to declare this source accepted. CPU detection took several minutes even for this four-second excerpt; full-video throughput needs optimization and measurement before release. No full render was approved for this source.

## Required ten-video acceptance

Use 10 distinct full source videos, including at least two with Chinese subtitles near the bottom and two with two-line originals. Include Chinese–English original text and a rare low-position subtitle case. Record the original input hash and label actual subtitle blocks independently of the detector.

For each source: prepare; inspect five previews; record the automatic result before any manual edit; approve the actual revision; export; then inspect the complete decoded output. For merged output, evaluate Y within each source interval, not across cuts between sources.

| Source/hash | Duration / dimensions | Near bottom / two lines / bilingual | Auto Y / extension / fallback | Manual change | Y drift px | Collisions | Clipped accents | >2 lines | Pre-encode original-region differences | Runtime | Result |
|---|---|---|---|---|---|---|---|---|---|---|---|

Acceptance thresholds: zero per-source Y drift, zero observed overlaps, zero clipped `ệ ợ ữ ậ ỗ ằ`, zero cues exceeding two lines, and no compositing changes to original subtitle pixels. At least 9/10 automatic positions must be correct without manual changes. Do not compare CRF 18 decoded pixels bit-for-bit against the source as a lossless-codec test.

The ten-video review and full-output approval remain a release acceptance step. Do not mark this table passed from unit tests, an excerpt, or a set of videos that lacks the required cases. Windows package construction can be checked on Linux; Windows runtime behavior requires an actual Windows smoke run.

## Package and local launch

The 0.4.0 wheel must include `app/assets/fonts/BeVietnamPro-Regular.ttf` and `app/assets/fonts/OFL.txt`. Desktop installation includes PySide6 and PyAV. Both Linux and Windows release installers refer to the same version.

For this machine's isolated implementation checkout, launch without replacing the existing installed application:

```bash
cd /home/dluowng/subreplace-studio/.worktrees/fixed-subtitles
/home/dluowng/subreplace-studio/.venv/bin/python -m app.main
```

Use the **Duyệt phụ đề Việt → Mở lại lô** button to load the QA `batch.json`. Large inference work runs in a background thread; cancel is available on the Process page. The existing desktop shortcut continues to point to its installed runtime until an installation update is performed.
