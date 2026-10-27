#!/bin/sh
# Keep the phone's Dolphin 8B reachable from this PC, surviving the things that actually
# break it: a changed DHCP address, the wireless-debugging port changing, the PC's adb
# server restarting, and the phone's llama.cpp server dying.
#
# Discovery order:
#   1. an already-connected wireless transport (serial contains ':')
#   2. mDNS (_adb._tcp) - this is the layer that survives a changed IP or port
#   3. the last IP we saved
#   4. USB: put adbd back in tcp mode and read the phone's own Wi-Fi address
#
# Then: forward localhost:$PORT -> phone, start the phone's llama.cpp server when it is
# down (detached with setsid - `adb tcpip` kills plain background children), and optionally
# open the chat window.
#
#   scripts/dolphin_up.sh [--no-open]
#
# Env: DOLPHIN_PORT (default 9931), DOLPHIN_PHONE_IP (skip discovery, use this IP).
set -eu

PORT="${DOLPHIN_PORT:-9931}"
URL="http://127.0.0.1:${PORT}/"
DIR=/data/local/tmp/llama-b11913
MODEL=/sdcard/Download/Dolphin3.0-Llama3.1-8B-Q4_K_M.gguf
LOG=/sdcard/Download/dolphin-server.log
STATE="${MEGAZWORD_HOME:-$HOME/.megazword}"
IPFILE="$STATE/dolphin-phone.ip"
OPEN=1
[ "${1:-}" = "--no-open" ] && OPEN=0

mkdir -p "$STATE"
command -v adb >/dev/null 2>&1 || { echo "adb is not installed" >&2; exit 1; }
adb start-server >/dev/null 2>&1 || true

all_devices() { adb devices | awk 'NR>1 && $2=="device"{print $1}'; }
wireless() { all_devices | grep ':' | head -1 || true; }
usb() { all_devices | grep -v ':' | head -1 || true; }
mdns_addr() { adb mdns services 2>/dev/null | awk '$2=="_adb._tcp"{print $3; exit}' || true; }

SERIAL=$(wireless)

# 2. mDNS by name - survives a changed IP or port
if [ -z "$SERIAL" ]; then
  ADDR=$(mdns_addr)
  if [ -n "$ADDR" ]; then
    adb connect "$ADDR" >/dev/null 2>&1 || true
    SERIAL=$(wireless)
  fi
fi

# 3. last saved IP
if [ -z "$SERIAL" ]; then
  IP="${DOLPHIN_PHONE_IP:-$(cat "$IPFILE" 2>/dev/null || true)}"
  if [ -n "$IP" ]; then
    adb connect "${IP}:5555" >/dev/null 2>&1 || true
    SERIAL=$(wireless)
  fi
fi

# 4. USB: re-enter tcp mode and learn the current Wi-Fi address (this is the reboot path)
if [ -z "$SERIAL" ]; then
  U=$(usb)
  if [ -n "$U" ]; then
    echo "usb found; re-enabling wireless adb"
    adb -s "$U" tcpip 5555 >/dev/null 2>&1 || true
    sleep 2
    IP=$(adb -s "$U" shell 'ip -f inet addr show wlan0 2>/dev/null' 2>/dev/null \
          | awk '/inet /{print $2}' | cut -d/ -f1 | head -1 || true)
    if [ -n "$IP" ]; then
      adb connect "${IP}:5555" >/dev/null 2>&1 || true
      SERIAL=$(wireless)
    fi
  fi
fi

if [ -z "$SERIAL" ]; then
  echo "no phone reachable (mDNS, saved IP and USB all failed)" >&2
  exit 1
fi
echo "device: $SERIAL"

case "$SERIAL" in
  *:*) echo "${SERIAL%:*}" > "$IPFILE" ;;
esac

adb -s "$SERIAL" forward "tcp:${PORT}" "tcp:${PORT}" >/dev/null
echo "tunnel up: $(adb -s "$SERIAL" forward --list | grep ":${PORT} " || true)"

up() { curl -fs -m 5 "${URL}v1/models" >/dev/null 2>&1; }

if ! up; then
  echo "starting phone server from ${DIR}"
  adb -s "$SERIAL" shell "cd ${DIR} && LD_LIBRARY_PATH=${DIR} setsid nohup ./llama-server \
    -m ${MODEL} -c 2048 -t 6 --host 127.0.0.1 --port ${PORT} >${LOG} 2>&1 </dev/null &" >/dev/null 2>&1 || true
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do sleep 5; up && break; done
fi

if ! up; then
  echo "server not answering; see ${LOG} on the phone" >&2
  exit 1
fi

if [ "$OPEN" = 1 ]; then
  echo "Dolphin 8B up - opening ${URL}"
  if command -v chromium >/dev/null 2>&1; then
    setsid chromium --app="$URL" >/dev/null 2>&1 &
  else
    setsid xdg-open "$URL" >/dev/null 2>&1 &
  fi
  echo "opened."
fi
