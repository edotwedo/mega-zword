"""Wait for Phil: block on an ntfy stream until he posts in the Hive room.

Run it as a background command. It stays quiet until a ``hive:<n>`` ping arrives
or the local cache already holds an unseen message from Phil, then prints his
messages and exits, which wakes the session to check in. No polling loops.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.request
from pathlib import Path

from . import config
from .room import DEFAULT_ROOM, RemoteRoom, is_phil, room_dir

STREAM = "https://ntfy.sh/{topic}/json"
SIGNAL = re.compile(r"hive:\d+")
FIRST_DELAY = 5
MAX_DELAY = 300


def _last_id(path: Path) -> int:
    try:
        return int(json.loads(path.read_text(encoding="utf-8")).get("last", 0))
    except (OSError, ValueError, TypeError, AttributeError):
        return 0


def _save_last(path: Path, value: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"last": int(value)}), encoding="utf-8")


def _unseen(room_obj, last: int):
    """Only roster-unknown authors (Phil's lanes) are actionable, including ANNOUNCE lines."""
    return [m for m in room_obj.cached()
            if m.remote_id > last
            and is_phil(m.author)]


def _event(line) -> dict:
    try:
        data = json.loads(line.decode("utf-8") if isinstance(line, bytes) else line)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def wait_for_phil(room_obj, topic: str, state_path: Path,
                  opener=urllib.request.urlopen, sleep=time.sleep):
    """Block until Phil has a new Hive message; return the unseen ones."""
    state_path = Path(state_path)
    last = _last_id(state_path)
    room_obj.refresh()
    found = _unseen(room_obj, last)
    if found:
        _save_last(state_path, found[-1].remote_id)
        return found
    delay = FIRST_DELAY
    while True:
        try:
            with opener(STREAM.format(topic=topic), timeout=60) as stream:
                for raw in stream:
                    data = _event(raw)
                    if (data.get("event") == "message"
                            and SIGNAL.fullmatch(str(data.get("message", "")).strip())):
                        room_obj.refresh()
                        found = _unseen(room_obj, last)
                        if found:
                            _save_last(state_path, found[-1].remote_id)
                            return found
        except (OSError, ValueError, KeyError, TypeError):
            pass
        sleep(delay)
        delay = min(delay * 2, MAX_DELAY)


def seat_topic(seat: str) -> str:
    """Deterministic per-seat ntfy topic, so escalation can page one seat."""
    slug = re.sub(r"[^a-z0-9]+", "-", (seat or "").strip().lower()).strip("-")
    return f"megazword-hive-seat-{slug}" if slug else ""


def default_state(room: str) -> Path:
    """Per-seat bookmark, so one waiter cannot consume another seat's messages."""
    seat = os.environ.get("MEGAZWORD_SEAT") or f"pid-{os.getpid()}"
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", seat)
    return room_dir() / f"{room}.{safe}.wait.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--room", default=DEFAULT_ROOM)
    parser.add_argument("--topic", default="megazword-hive", help="ntfy topic the room pings")
    parser.add_argument("--state", type=Path, help="cursor file (default: rooms/<room>.wait.json)")
    args = parser.parse_args(argv)
    state = args.state or default_state(args.room)
    room_obj = RemoteRoom(args.room, config.load(), None)
    for message in wait_for_phil(room_obj, args.topic, state):
        print(f"{message.time} [{message.author}] {message.text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
