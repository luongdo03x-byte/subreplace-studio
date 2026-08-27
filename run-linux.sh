#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT_DIR/.venv"
PYTHON="${SUBREPLACE_PYTHON:-python3}"

"$PYTHON" -c 'import sys; assert (3, 11) <= sys.version_info < (3, 14), "Python 3.11-3.13 is required"'
if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then
  echo "FFmpeg and FFprobe are required. Install the ffmpeg package, then run this script again." >&2
  exit 2
fi

if [[ ! -x "$VENV/bin/subreplace-studio" ]]; then
  "$PYTHON" -m venv "$VENV"
  "$VENV/bin/python" -m pip install --upgrade pip wheel
  "$VENV/bin/python" -m pip install -e "$ROOT_DIR[desktop,media,ai,cloud]"
fi

exec "$VENV/bin/subreplace-studio" "$@"
