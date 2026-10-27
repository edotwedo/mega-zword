#!/bin/sh
# Install Mega Zword on Linux. Mirrors scripts/install.ps1: prefer pipx, else a venv, put the
# command on PATH, and finish by checking the install. Safe to run again after an update.
#
#   scripts/install.sh
#
# Nothing here needs root: everything lands under ~/.local.
set -eu

repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
say() { printf '%s\n' "$*"; }

say "Mega Zword installer (Linux)"
say "repo: $repo"
say

python=python3
command -v "$python" >/dev/null 2>&1 || python=python
command -v "$python" >/dev/null 2>&1 || { say "error: python3 not found (need 3.11+)" >&2; exit 1; }
say "python: $("$python" -c 'import sys; print(sys.version.split()[0])')"

if command -v pipx >/dev/null 2>&1; then
  say "pipx found - installing an editable install"
  pipx install --force -e "$repo" >/dev/null
  mg=$(command -v megazword || true)
else
  venv="$HOME/.local/share/megazword-venv"
  say "pipx not found - using a venv at $venv"
  [ -d "$venv" ] || "$python" -m venv "$venv"
  "$venv/bin/python" -m pip install --disable-pip-version-check -q --upgrade pip
  "$venv/bin/python" -m pip install --disable-pip-version-check -q -e "$repo"
  mkdir -p "$HOME/.local/bin"
  ln -sf "$venv/bin/megazword" "$HOME/.local/bin/megazword"
  mg="$HOME/.local/bin/megazword"
fi

if [ -z "${mg:-}" ] || [ ! -x "$mg" ]; then
  say "error: the megazword command was not installed" >&2
  exit 1
fi
say "installed: $mg"
say

case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) say "WARNING: ~/.local/bin is not on PATH. Add it with:"
     say "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
     say "" ;;
esac

say "checking the install:"
"$mg" --version
"$mg" doctor || say "(doctor reported a problem above - that is your setup, not the install)"

say
say "Optional: for the native window instead of the Chromium app window, install"
say "  pywebview plus GTK/WebKit2 (python-gobject, webkit2gtk-4.1) and rerun."
say
say "Next steps:"
say "  megazword init          # write a default config from the AIs it finds"
say "  megazword room show     # read the Hive"
say "  megazword dashboard     # local web page"
