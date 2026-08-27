#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WHEEL="$SCRIPT_DIR/subreplace_studio-0.2.2-py3-none-any.whl"
if [[ ! -f "$WHEEL" ]]; then
  WHEEL="$ROOT_DIR/dist/subreplace_studio-0.2.2-py3-none-any.whl"
fi
INSTALL_DIR="${SUBREPLACE_INSTALL_DIR:-$HOME/.local/share/subreplace-studio/runtime}"
BIN_DIR="${SUBREPLACE_BIN_DIR:-$HOME/.local/bin}"
DESKTOP_DIR="$HOME/.local/share/applications"

if [[ ! -f "$WHEEL" ]]; then
  echo "Release wheel not found: $WHEEL" >&2
  exit 2
fi

PYTHON="${SUBREPLACE_PYTHON:-python3}"
"$PYTHON" -c 'import sys; assert (3, 11) <= sys.version_info < (3, 14), "Python 3.11-3.13 is required"'

if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then
  if command -v apt-get >/dev/null; then
    sudo apt-get update
    sudo apt-get install -y ffmpeg
  elif command -v dnf >/dev/null; then
    sudo dnf install -y ffmpeg
  elif command -v pacman >/dev/null; then
    sudo pacman -S --needed ffmpeg
  else
    echo "Install FFmpeg and FFprobe, then run this installer again." >&2
    exit 2
  fi
fi

mkdir -p "$INSTALL_DIR" "$BIN_DIR" "$DESKTOP_DIR"
"$PYTHON" -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/python" -m pip install --upgrade pip wheel
"$INSTALL_DIR/.venv/bin/python" -m pip install "$WHEEL[desktop,media,ai,cloud]"

cat > "$BIN_DIR/subreplace-studio" <<EOF
#!/usr/bin/env bash
exec "$INSTALL_DIR/.venv/bin/subreplace-studio" "\$@"
EOF
cat > "$BIN_DIR/subreplace-batch" <<EOF
#!/usr/bin/env bash
exec "$INSTALL_DIR/.venv/bin/subreplace-batch" "\$@"
EOF
chmod +x "$BIN_DIR/subreplace-studio" "$BIN_DIR/subreplace-batch"
cat > "$DESKTOP_DIR/subreplace-studio.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=SubReplace Studio
Exec=$BIN_DIR/subreplace-studio
Terminal=false
Categories=AudioVideo;Utility;
EOF

echo "Installed SubReplace Studio 0.2.2"
echo "Launch: $BIN_DIR/subreplace-studio"
echo "Application menu shortcut: $DESKTOP_DIR/subreplace-studio.desktop"
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  echo "Add $BIN_DIR to PATH to launch it by name."
fi
