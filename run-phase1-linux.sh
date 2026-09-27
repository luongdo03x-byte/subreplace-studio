#!/usr/bin/env bash
set -euo pipefail

OVERLAY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OVERLAY_PYTHON="${SUBREPLACE_RUNTIME_PYTHON:-$OVERLAY_ROOT/.venv/bin/python}"
if [[ ! -x "$OVERLAY_PYTHON" ]]; then
  OVERLAY_GIT_COMMON="$(git -C "$OVERLAY_ROOT" rev-parse --path-format=absolute --git-common-dir)"
  OVERLAY_PYTHON="$(dirname "$OVERLAY_GIT_COMMON")/.venv/bin/python"
fi
if [[ ! -x "$OVERLAY_PYTHON" ]]; then
  echo 'Install the desktop, media and AI dependencies, or set SUBREPLACE_RUNTIME_PYTHON.' >&2
  exit 2
fi
cd "$OVERLAY_ROOT"
exec "$OVERLAY_PYTHON" -m app.main "$@"
