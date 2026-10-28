"""Hive room sentry for all Hive seats.

Monitors the Hive room for actionable messages or unclaimed assignments.
Uses Jev (TypeSafe System One) when TYPESAFE_API_KEY is available, or
local heuristic rules otherwise, to judge whether an incoming message
requires action for a specific seat (or any active seat).

Exits with code 0 as soon as an actionable message is detected, waking
up the agent reactively without burning frontier LLM tokens while idle.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

from . import config, decision, room

log = logging.getLogger("megazword.sentry")

# Common seat aliases mapping base names to designations
SEAT_ALIASES = {
    "gavin-27": ["gavin", "gavin-27"],
    "mike-54": ["mike", "mike-54"],
    "billy-55": ["billy", "billy-55"],
    "wenwei-56": ["wenwei", "wen-wei", "wenwei-56"],
    "paul-53": ["paul", "paul-53"],
    "cinder-21": ["cinder", "cinder-21"],
    "commandersmith": ["commandersmith", "smith"],
    "therock": ["therock", "the rock", "briar-20"],
    "patcher": ["patcher", "briar-22"],
}


def get_seat_patterns(seat: str) -> list[str]:
    s = seat.strip().lower()
    return SEAT_ALIASES.get(s, [s, s.split("-")[0]])


def get_state_file(seat: str, room_name: str = "hive", home: Path | None = None) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", seat)
    base_home = home or config.HOME
    return base_home / f"sentry.{room_name}.{safe}.json"


def load_last_id(state_file: Path) -> int:
    try:
        if state_file.exists():
            data = json.loads(state_file.read_text(encoding="utf-8"))
            return int(data.get("last_id", 0))
    except Exception:
        pass
    return 0


def save_last_id(state_file: Path, last_id: int) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({"last_id": last_id, "updated_at": time.time()}), encoding="utf-8")


def check_actionable_jev(text: str, seat: str) -> bool:
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key:
        return False
    try:
        question = {
            "is_actionable": {
                "type": "noul",
                "instructions": (
                    f"Determine if this message in a collaborative developer chat room is an actionable directive, "
                    f"task assignment, code review request, or unclaimed work for agent seat '{seat}' (or open "
                    f"to any unassigned seat). Informational notes, status summaries of finished work, corrections, "
                    f"and closing reports are FALSE."
                ),
                "statement": f"This message requires agent action or execution from {seat} or is an unclaimed task.",
            }
        }
        jd = decision.JevDecision(key)
        res = jd.choose(state={"message": text, "target_seat": seat}, questions=question)
        prob = decision.noul_probability(res.get("is_actionable", {}))
        if prob is not None:
            return prob >= 0.5
    except Exception as exc:
        log.warning("Jev evaluation error: %s", exc)
    return False


def check_actionable_heuristic(msg: room.RoomMessage, seat: str) -> bool:
    author = (msg.author or "").lower()
    text = msg.text or ""
    patterns = get_seat_patterns(seat)

    # Don't react to our own seat's messages
    for p in patterns:
        if p in author:
            return False
        prefix = text.strip().lower()
        if prefix.startswith(p + ":") or prefix.startswith(p + " -") or prefix.startswith(p + " ->"):
            # If it's a report of work done or status, ignore it
            if any(w in prefix for w in ["complete", "done", "landed", "resolved", "pass", "finished", "claiming"]):
                return False

    # Skip closing summaries or completed work reports
    if text.startswith("CLOSING SUMMARY") or "All three items are done" in text:
        return False

    # Direct mention of this seat or its alias
    for p in patterns:
        regex = r"\b" + re.escape(p) + r"\b"
        if re.search(regex, text, re.IGNORECASE):
            # Check for directive intent
            if any(w in text.lower() for w in ["assign", "review", "merge", "fix", "do", "run", "claim", "outstanding", "complete"]):
                return True

    # Any message from Phil
    if room.is_phil(author):
        return True

    # Open unassigned work / multi-assignment broadcasts
    if re.search(r"\b(unclaimed|open to any|FOUR ASSIGNMENTS|ASSIGN ->)\b", text, re.IGNORECASE):
        # If explicitly assigned to another specific seat, skip
        if not re.search(r"ASSIGN -> (?!(" + "|".join(re.escape(p) for p in patterns) + r"))\w+", text, re.IGNORECASE):
            return True

    return False


def is_actionable(msg: room.RoomMessage, seat: str) -> bool:
    if os.environ.get("TYPESAFE_API_KEY", "").strip():
        return check_actionable_jev(msg.text, seat)
    return check_actionable_heuristic(msg, seat)


def run_sentry(seat: str, room_name: str = "hive", poll_interval: int = 15, timeout: int | None = None, home: Path | None = None) -> int:
    cfg = config.load()
    base_home = home or config.HOME
    remote = room.RemoteRoom(room_name, cfg, base_home)
    state_file = get_state_file(seat, room_name, base_home)
    
    last_id = load_last_id(state_file)
    if last_id == 0:
        # Initialize bookmark to latest current message so we only wake on NEW messages
        try:
            remote.refresh()
            cached = remote.cached()
            if cached:
                last_id = cached[-1].remote_id
                save_last_id(state_file, last_id)
        except Exception:
            pass

    start_time = time.time()
    print(f"[sentry] Sentry started for seat '{seat}' in room '{room_name}'. Tracking after remote_id {last_id}. Poll every {poll_interval}s.", flush=True)

    while True:
        try:
            remote.refresh()
            messages = remote.cached()
            new_messages = [m for m in messages if m.remote_id > last_id]
            
            for msg in new_messages:
                last_id = max(last_id, msg.remote_id)
                save_last_id(state_file, last_id)
                if is_actionable(msg, seat):
                    print(f"\n=== ACTIONABLE MESSAGE DETECTED FOR {seat} (ID {msg.remote_id}) ===", flush=True)
                    print(f"Author: {msg.author}\nTime: {msg.time}\n\n{msg.text}\n", flush=True)
                    print("==========================================================", flush=True)
                    return 0
        except Exception as exc:
            log.warning("Error checking room: %s", exc)

        if timeout and (time.time() - start_time) >= timeout:
            print(f"[sentry] Timeout of {timeout}s reached with no actionable messages.", flush=True)
            return 1

        time.sleep(poll_interval)


def main(argv: list[str] | None = None) -> int:
    default_seat = os.environ.get("MEGAZWORD_SEAT") or "MIKE-54"
    parser = argparse.ArgumentParser(description="Hive room sentry for all seats")
    parser.add_argument("--seat", default=default_seat, help=f"Seat designation to filter for (default: {default_seat})")
    parser.add_argument("--room", default="hive", help="Hive room name (default: hive)")
    parser.add_argument("--interval", type=int, default=15, help="Poll interval in seconds (default: 15)")
    parser.add_argument("--timeout", type=int, default=None, help="Optional timeout in seconds")
    parser.add_argument("--init-now", action="store_true", help="Set bookmark to latest current message and exit")
    args = parser.parse_args(argv)

    state_file = get_state_file(args.seat, args.room)
    if args.init_now:
        cfg = config.load()
        remote = room.RemoteRoom(args.room, cfg, config.HOME)
        remote.refresh()
        cached = remote.cached()
        if cached:
            save_last_id(state_file, cached[-1].remote_id)
            print(f"Initialized sentry bookmark for {args.seat} to remote_id {cached[-1].remote_id}")
        return 0

    return run_sentry(seat=args.seat, room_name=args.room, poll_interval=args.interval, timeout=args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
