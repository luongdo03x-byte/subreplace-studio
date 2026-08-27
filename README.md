# SubReplace Studio 0.2.2

SubReplace Studio removes burned-in Chinese dialogue subtitles, protects watermark text, translates the recovered dialogue, and renders replacement subtitles at the original anchors.

## Clone And Run

The first run creates a local `.venv` and installs the application dependencies. Git, Python 3.11-3.13, FFmpeg, and FFprobe must already be available.

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

Later launches only require `./run-linux.sh` or `.\run-windows.ps1`. AI models are downloaded on demand during the first processing job.

## Requirements

- Windows 10/11 64-bit or a current 64-bit Linux distribution.
- Python 3.11-3.13. Python 3.12 is recommended.
- FFmpeg and FFprobe on `PATH`.
- At least 8 GB RAM and 5 GB free disk space.
- Internet access on first run for PaddleOCR and Whisper model downloads.
- An OpenAI or Gemini API key, a compatible custom endpoint, or a configured local translation command.

CUDA is optional. The classical eraser and CPU OCR path work without an NVIDIA GPU.

## Install

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

Launch the desktop UI with `subreplace-studio`, or use `subreplace-batch --help` for automation.

## Portable behavior

- User settings and model component paths are stored under the operating system user data directory.
- API keys can be remembered through the operating system keyring and are not written into project files.
- PaddleOCR and Whisper download their model files on first use.
- Each video receives its own project cache; no event or timing from another video is reused.
- Finished videos and SRT files from different projects can be published into one output folder with source-based filenames.

Version 0.2.2 adds frame-level recovery for subtitle intervals missed by the primary detector, high-pass residual gates, bright-glyph plus temporal masks, Navier-Stokes reconstruction, and stroke-level watermark protection.
