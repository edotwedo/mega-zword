#!/bin/sh
# Poke a Hive seat's tab: inject a line and press Enter.
#
# Linux stand-in for scripts/hive_respond.ps1, which did this with SendKeys on Windows.
# A seat is an interactive CLI in its own kitty tab, so it does not poll the room and does
# not self-schedule (M5) - it only moves when something writes to it. Without this, live seats
# sit idle: on 2026-10-26 MIKE-54 and WenWei-56 claimed their tasks within seconds of a poke
# after sitting idle for two hours.
#
#   scripts/hive_poke.sh --list                 # window titles in the Hive kitty
#   scripts/hive_poke.sh <title> "<message>"    # send text, then Enter, to that window
#   scripts/hive_poke.sh --all "<message>"      # every seat window except the conductor's
#
# The socket is the one scripts/hive_resume.sh starts kitty with.
set -eu

sock="${KITTY_HIVE_SOCKET:-${XDG_RUNTIME_DIR:-/tmp}/kitty-hive.sock}"
[ -S "$sock" ] || { echo "no kitty Hive socket at $sock (is the Hive kitty running?)" >&2; exit 1; }

titles() {
  kitten @ --to "unix:$sock" ls | python3 -c '
import json, sys
print("\n".join(sorted({w.get("title", "")
                        for os_window in json.load(sys.stdin)
                        for tab in os_window["tabs"]
                        for w in tab["windows"]} - {""})))'
}

case "${1:-}" in
  --list|"")
    titles
    exit 0
    ;;
  --all)
    msg="${2:?message required}"
    for t in $(titles); do
      case "$t" in *Megazword*) continue ;; esac   # skip the conductor's own tab
      "$0" "$t" "$msg" || true
    done
    exit 0
    ;;
esac

title="$1"
msg="${2:?message required}"
kitten @ --to "unix:$sock" send-text --match "title:$title" "$msg"
sleep 0.4
kitten @ --to "unix:$sock" send-key --match "title:$title" enter
echo "poked $title"
