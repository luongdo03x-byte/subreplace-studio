#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$ROOT_DIR/.venv/bin/python"
APP="$ROOT_DIR/.venv/bin/subreplace-studio-next"

if [[ ! -x "$PYTHON" || ! -x "$APP" ]]; then
  echo "SubReplace Studio Next runtime is not installed."
  echo "Run: uv venv .venv --python 3.13"
  echo "Then: uv pip install --python .venv/bin/python --editable '.[desktop,youtube,cloud,media]'"
  exit 1
fi

exec "$APP" "$@"
