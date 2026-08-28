#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT_DIR/.venv"

supports_python() {
  "$1" -c 'import sys; raise SystemExit(0 if (3, 11) <= sys.version_info < (3, 14) else 1)' >/dev/null 2>&1
}

PYTHON="${SUBREPLACE_PYTHON:-}"
if [[ -n "$PYTHON" ]] && ! supports_python "$PYTHON"; then
  echo "SUBREPLACE_PYTHON must point to Python 3.11-3.13." >&2
  exit 2
fi
if [[ -z "$PYTHON" ]]; then
  for candidate in "$HOME/.local/bin/python3.13" "$HOME/.local/bin/python3.12" "$HOME/.local/bin/python3.11" python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null && supports_python "$candidate"; then
      PYTHON="$(command -v "$candidate")"
      break
    fi
  done
fi
UV="$(command -v uv 2>/dev/null || true)"
if [[ -z "$UV" && -x "$HOME/.local/bin/uv" ]]; then
  UV="$HOME/.local/bin/uv"
fi
if [[ -z "$PYTHON" && -n "$UV" ]]; then
  echo "Installing a managed Python 3.13 runtime with uv..."
  "$UV" python install 3.13
  PYTHON="$("$UV" python find 3.13)"
fi
if [[ -z "$PYTHON" ]] || ! supports_python "$PYTHON"; then
  echo "Python 3.11-3.13 is required. Install Python 3.13 or uv, then run this script again." >&2
  exit 2
fi

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
