#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
BUILD_PYTHON="${SUBREPLACE_BUILD_PYTHON:-python3}"
BUILD_VENV="$ROOT_DIR/.build-venv"
"$BUILD_PYTHON" -m venv "$BUILD_VENV"
"$BUILD_VENV/bin/python" -m pip install --quiet --upgrade pip build
rm -rf build dist *.egg-info
"$BUILD_VENV/bin/python" -m build --wheel
"$BUILD_VENV/bin/python" -m zipfile -c "dist/subreplace-studio-0.3.0-linux.zip" \
  "dist/subreplace_studio-0.3.0-py3-none-any.whl" \
  "installers/install-linux.sh" README.md
"$BUILD_VENV/bin/python" -m zipfile -c "dist/subreplace-studio-0.3.0-windows.zip" \
  "dist/subreplace_studio-0.3.0-py3-none-any.whl" \
  "installers/install-windows.ps1" README.md
(
  cd dist
  sha256sum \
    subreplace_studio-0.3.0-py3-none-any.whl \
    subreplace-studio-0.3.0-linux.zip \
    subreplace-studio-0.3.0-windows.zip > SHA256SUMS
)
