# SubReplace Studio

SubReplace Studio is a local Windows/Linux desktop pipeline for replacing hard-coded Chinese dialogue subtitles with Vietnamese or English while preserving watermark/logo pixels and reconstructing the original background.

**Non-negotiable eraser rule:** no black rectangles, blur boxes, solid overlays, crop/zoom tricks, or target text drawn over unerased Chinese. Low-confidence reconstruction is routed to review or to a user-installed temporal inpainting provider.

## Implemented workflow

`source video → media probe → adaptive full-frame text events → PaddleOCR → optional faster-whisper ASR → dialogue/watermark classification → protected stroke-mask erase → translation → FFmpeg/libass render → review/preview/export`

The desktop application also includes:

- event-driven OCR so stable text is OCR'd once per event rather than every frame;
- isolated JSONL subprocess workers for heavyweight stages and VRAM release;
- durable jobs with failed-stage retry, resume and cancellation;
- versioned runtime/component management with SHA-256 verification and atomic activation;
- ProPainter/E2FGVI plugin validation and explicit license acceptance;
- Subtitle Editor for OCR/translation edits and Needs Review decisions;
- synchronized Original/Replaced preview;
- portable `.subreplace` project packages and schema migration;
- sanitized diagnostics and export of final MP4/SRT/clean video/project archive.

## Install for development

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python scripts/check_no_cover_fallbacks.py
python scripts/check_commercial_build.py
python scripts/check_runtime_manifests.py
```

## Desktop

```bash
python -m pip install -e '.[desktop]'
subreplace-studio
```

For production OCR/ASR:

```bash
python -m pip install -e '.[ai]'
```

Cloud translation providers are optional:

```bash
python -m pip install -e '.[cloud]'
```

## Batch CLI

```bash
subreplace-batch --help
```

API keys are read from a named environment variable rather than accepted as raw CLI values, to avoid exposing secrets in the process list.

## Temporal inpainting plugins

ProPainter and E2FGVI are **not bundled**. The user selects an upstream plugin folder/weights in Model Manager and explicitly accepts the corresponding provider license. SubReplace validates required files before processing and still composes provider output only inside the effective subtitle mask.

## Project/export

`.subreplace` packages support lightweight, portable, and archive modes. Export can produce final MP4, SRT, optional lossless clean video, and a portable project package.

## Quality and verification status

Functional completion and reconstruction quality are separate. The seven-metric reconstruction thresholds are never relaxed to make a build look green. See `docs/STATUS.md` for the current environment limitations and quality caveat.
