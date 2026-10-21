"""One-pass escalation for unanswered calls from Phil; no timer or model calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .filelock import locked, write_atomic
from .room import DEFAULT_ROOM, RemoteRoom, room_dir
from .room_wait import PHIL_AUTHORS, seat_topic

DESIGNATION = re.compile(r"^[A-Za-z]+-\d+\b")
ROSTER = Path(__file__).resolve().parents[2] / "docs" / "HIVE-ROSTER.md"
PHONE_BODY = "Nobody picked up Phil's Hive message"
MAX_AGE = 60 * 60  # older calls are history, not emergencies: never escalate them


@dataclass(frozen=True)
class Action:
    call_id: int
    step: int
    seat: str | None
    body: str


def _time(value) -> datetime:
    if not isinstance(value, datetime):
        value = datetime.fromisoformat(value)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def escalate(messages, now, roster, state) -> list[Action]:
    """Return due actions and mark their steps in the supplied JSON-safe state.

    Explicit replies name a call as hive:ID, #ID, call ID or message ID.
    The runner persists only successfully sent steps, so failed sends can retry.
    """
    now = _time(now)
    timed = []
    for message in messages:
        try:
            stamp = _time(message.time)
        except (TypeError, ValueError):
            continue
        if stamp <= now:
            timed.append((message, stamp))
    actions = []
    seats = list(roster or [])[:2]
    for call, stamp in timed:
        if call.author not in PHIL_AUTHORS or call.remote_id <= 0:
            continue
        if (now - stamp).total_seconds() > MAX_AGE:
            continue
        reference = re.compile(
            rf"(?:\bhive:\s*|#|\b(?:call|message)\s+#?){call.remote_id}\b", re.I)
        answered = any(
            reply.remote_id > call.remote_id and reply_time >= stamp
            and reply.author != call.author
            and (DESIGNATION.match(reply.text.lstrip()) or reference.search(reply.text))
            for reply, reply_time in timed)
        if answered:
            continue
        done = state.setdefault(str(call.remote_id), [])
        for step, minutes in enumerate((5, 10, 15), 1):
            if step in done or (now - stamp).total_seconds() < minutes * 60:
                continue
            if step < 3 and len(seats) < step:
                continue
            actions.append(Action(call.remote_id, step,
                                  seats[step - 1] if step < 3 else None,
                                  f"hive:{call.remote_id}" if step < 3 else PHONE_BODY))
            done.append(step)
    return actions


def read_roster(path: Path | None = None) -> list[str]:
    if path is None:
        # Installed CLIs can still find the checkout they are invoked inside.
        path = next((root / "docs" / "HIVE-ROSTER.md"
                     for root in (Path.cwd(), *Path.cwd().parents)
                     if (root / "docs" / "HIVE-ROSTER.md").is_file()), ROSTER)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return []
    # Both tables contain seats; preserve first appearance, without duplicates.
    return list(dict.fromkeys(re.findall(r"^\|\s*([A-Za-z]{3,}-?\d{1,4})\s*\|", text, re.M)))


def topics(cfg) -> tuple[str, str]:
    """Use the PC override used by announce, or Worker-style topic settings."""
    return tuple(os.environ.get(f"MEGAZWORD_NTFY_{kind}_TOPIC")
                 or os.environ.get(f"NTFY_{kind}_TOPIC")
                 or getattr(cfg, f"room_ntfy_{kind.lower()}_topic", "")
                 for kind in ("PC", "PHONE"))


def send(topic: str, body: str) -> None:
    request = urllib.request.Request(f"https://ntfy.sh/{topic}",
                                     data=body.encode("utf-8"), method="POST")
    with urllib.request.urlopen(request, timeout=8):
        pass


def run_pass(room_obj, now, roster, state_path: Path, pc_topic: str,
             phone_topic: str, sender=send) -> list[Action]:
    if not pc_topic and not phone_topic:
        return []
    with locked(state_path) as acquired:
        if not acquired:
            raise OSError("escalation state busy")
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        if not isinstance(state, dict) or any(
                not isinstance(steps, list) or any(type(step) is not int for step in steps)
                for steps in state.values()):
            raise ValueError("invalid escalation state")
        room_obj.refresh()
        planned = json.loads(json.dumps(state))
        actions = escalate(room_obj.cached(), now, roster, planned)
        sent = []
        for action in actions:
            if action.step < 3:
                # Page the one seat whose turn it is, not the whole PC.
                topic = (seat_topic(action.seat) or pc_topic) if pc_topic else ""
            else:
                topic = phone_topic
            if not topic:
                continue
            sender(topic, action.body)
            state.setdefault(str(action.call_id), []).append(action.step)
            write_atomic(state_path, json.dumps(state))
            sent.append(action)
        return sent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--room", default=DEFAULT_ROOM)
    args = parser.parse_args(argv)
    cfg = config.load()
    pc, phone = topics(cfg)
    if not pc and not phone:
        print("No escalation topics configured; no sends.")
        return 0
    try:
        room_obj = RemoteRoom(args.room, cfg, None)
        # One shared ledger per origin/room, next to room_wait's bookmarks.
        origin = hashlib.sha256(room_obj.url.encode()).hexdigest()[:24]
        binding = f"{args.room}.{origin}"
        sent = run_pass(room_obj, datetime.now(timezone.utc), read_roster(),
                        room_dir() / f"{binding}.escalate.json", pc, phone)
    except (OSError, ValueError, TypeError) as exc:
        print(f"Escalation failed: {exc}")
        return 2
    for action in sent:
        print(f"Call {action.call_id}: step {action.step} sent to {action.seat or 'phone'}.")
    if not sent:
        print("No escalation sends due.")
    return 0
