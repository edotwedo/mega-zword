#!/usr/bin/env bash
# Install Mega Zword for this Linux user from this checkout.
#
#   scripts/install.sh            install editable package and verify doctor
#   scripts/install.sh --shortcut also install desktop entry (~/.local/share/applications/megazword.desktop)
set -euo pipefail

SHORTCUT=false
while (($#)); do
  case "$1" in
    -s|--shortcut)
      SHORTCUT=true
      shift
      ;;
    *)
      echo "Usage: scripts/install.sh [-s|--shortcut]" >&2
      exit 1
      ;;
  esac
done

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="${HOME}/.local/bin"
mkdir -p "$BIN_DIR"

# Ensure ~/.local/bin is on PATH in interactive rc files
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  export PATH="$BIN_DIR:$PATH"
  for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
    if [ -f "$rc" ] && ! grep -q 'HOME/.local/bin' "$rc" 2>/dev/null; then
      echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$rc"
    fi
  done
fi

if command -v pipx &>/dev/null; then
  echo "Installing with pipx..."
  pipx install --force -e "$REPO"
  MZ_BIN="$BIN_DIR/megazword"
  if [ ! -x "$MZ_BIN" ]; then
    MZ_BIN="$(command -v megazword || true)"
  fi
else
  VENV="$REPO/.venv"
  PYTHON="$VENV/bin/python3"
  if [ ! -x "$PYTHON" ]; then
    echo "Creating virtual environment at $VENV..."
    python3 -m venv "$VENV"
  fi
  echo "Installing editable package in venv..."
  "$VENV/bin/pip" install -e "$REPO"
  ln -sf "$VENV/bin/megazword" "$BIN_DIR/megazword"
  MZ_BIN="$BIN_DIR/megazword"
fi

if [ -z "$MZ_BIN" ] || [ ! -x "$MZ_BIN" ]; then
  echo "Error: megazword binary not found after installation" >&2
  exit 1
fi

echo "Mega Zword installed at $MZ_BIN"

if [ "$SHORTCUT" = true ]; then
  echo "Installing desktop entry..."
  "$MZ_BIN" app install
fi

echo "Running megazword doctor..."
"$MZ_BIN" doctor || true
exit 0
