# SubReplace Studio 0.3.1

SubReplace Studio is a local Windows/Linux desktop pipeline for replacing burned-in Chinese dialogue subtitles with Vietnamese or English while preserving watermark pixels and reconstructing the original background.

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

Later launches only require `./run-linux.sh` or `.\run-windows.ps1`. PaddleOCR and Whisper models are downloaded on demand during the first processing job.

## Multi-Video Queue

- Select and reorder up to 10 videos.
- Process videos strictly one at a time to keep memory and GPU usage bounded.
- Produce one translated MP4 for every successful source.
- Optionally create one long MP4 in the selected order.
- Normalize dimensions, FPS, sample aspect ratio, and audio before concatenation.
- Skip failed videos while allowing successful videos to be merged.
- Delete temporary per-video project caches after each item in a multi-video batch.
- Sort numeric filenames naturally, for example `1.mp4`, `2.mp4`, `10.mp4`.
- Do not create matching SRT sidecars automatically, preventing duplicate subtitles in VLC.

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

Version 0.3.1 fixes low-disk batch startup, reports per-video failures, cleans temporary batch caches, and sorts numeric filenames naturally.
