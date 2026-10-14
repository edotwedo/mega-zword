"""Small, explicit session status cards. Reading a briefing never calls an AI."""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from . import config
from .filelock import locked, write_atomic
from .guard import scrub

FIELDS = ("doing", "done", "blocked", "next")
STATES = ("working", "waiting", "blocked", "done")
STALE_SECONDS = 1800


def _text(value, name, limit=1200):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f"{name} must be text of at most {limit} characters")
    # Terminal output must not interpret escape sequences from a status card.
    return scrub("".join(c for c in value if c.isprintable() or c == "\n")).strip()


def _seat(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value):
        raise ValueError("seat must be 1-64 letters, digits, underscores or hyphens")
    return value.lower()


def publish(body: dict, home: Path | None = None, now=None) -> dict:
    """Replace one seat's card atomically; this is a snapshot, not a heartbeat."""
    seat = _seat(body.get("seat") or os.environ.get("MEGAZWORD_SEAT", ""))
    state = body.get("state", "working")
    if state not in STATES:
        raise ValueError("state must be working, waiting, blocked or done")
    card = {"seat": seat, "state": state,
            "project": _text(body.get("project", ""), "project", 120),
            **{key: _text(body.get(key, ""), key) for key in FIELDS},
            "updated": (now or datetime.now(timezone.utc)).isoformat()}
    path = (home or config.HOME) / "briefings" / f"{seat}.json"
    with locked(path):
        write_atomic(path, json.dumps(card, ensure_ascii=False) + "\n")
    return card


def snapshot(home: Path | None = None, now=None) -> dict:
    now = now or datetime.now(timezone.utc)
    cards, unreadable = [], 0
    for path in sorted(((home or config.HOME) / "briefings").glob("*.json")):
        try:
            if path.stat().st_size > 20_000:
                raise ValueError("oversize card")
            card = json.loads(path.read_text(encoding="utf-8"))
            seat = _seat(card["seat"])
            stamp = datetime.fromisoformat(card["updated"])
            if stamp.tzinfo is None or card["state"] not in STATES:
                raise ValueError("invalid card")
            age = max(0, (now - stamp).total_seconds())
            cards.append({"seat": seat, "state": card["state"],
                          "project": _text(card.get("project", ""), "project", 120),
                          **{k: _text(card.get(k, ""), k) for k in FIELDS},
                          "updated": stamp.isoformat(), "age_seconds": int(age),
                          "stale": age > STALE_SECONDS})
        except (OSError, ValueError, TypeError, KeyError):
            unreadable += 1
    cards.sort(key=lambda c: (c["stale"], c["seat"]))
    return {"cards": cards, "unreadable": unreadable, "now": now.isoformat()}


def render(data: dict) -> str:
    lines = ["Catch me up — saved session reports (no AI calls)"]
    if not data["cards"]:
        lines.append("No reports yet. Each terminal must publish a card with megazword brief report.")
    for card in data["cards"]:
        age = f"{card['age_seconds'] // 60}m ago"
        lines.append(f"\n{card['seat']} · {card['state']} · {age}"
                     + (" · stale snapshot" if card["stale"] else "")
                     + (f" · {card['project']}" if card["project"] else ""))
        for field, label in zip(FIELDS, ("Working on", "Just done", "Blocked by", "Next")):
            lines.append(f"  {label}: {card[field] or 'not reported'}")
    if data["unreadable"]:
        lines.append(f"\nSkipped {data['unreadable']} unreadable report(s).")
    return "\n".join(lines)


def add_parser(sub):
    parser = sub.add_parser("brief", help="catch up from saved session reports; no AI calls")
    parser.add_argument("action", nargs="?", choices=("show", "report"), default="show")
    parser.add_argument("--seat", help="session designation (or MEGAZWORD_SEAT)")
    parser.add_argument("--project", default="")
    parser.add_argument("--state", choices=STATES, default="working")
    for field in FIELDS:
        parser.add_argument(f"--{field}", default="")


def track_run(function):
    """CLI jobs report their lifecycle; standalone AI terminals publish explicitly."""
    @wraps(function)
    def tracked(sent, prompt, chain, cfg, memory, rating, forced, *args, **kwargs):
        seat = os.environ.get("MEGAZWORD_SEAT") or f"run-{os.getpid()}"
        task = prompt.strip().splitlines()[0][:1000] if prompt.strip() else "Run task"

        def report(state, done="", blocked="", next_step=""):
            try:
                publish({"seat": seat, "project": memory.project, "state": state,
                         "doing": task if state == "working" else "",
                         "done": done, "blocked": blocked, "next": next_step})
            except (ValueError, OSError) as exc:
                print(f"[megazword] could not save session report: {type(exc).__name__}",
                      file=sys.stderr)

        report("working", next_step="Wait for the AI result")
        try:
            code = function(sent, prompt, chain, cfg, memory, rating, forced, *args, **kwargs)
        except BaseException:
            report("blocked", blocked="Run interrupted before completion",
                   next_step="Inspect the terminal and resume or hand off")
            raise
        if code == 0:
            report("done", done=f"Returned an answer for: {task}",
                   next_step="Review the answer and verify any claimed work")
        else:
            report("blocked", blocked=f"No usable answer for: {task}",
                   next_step="Inspect the terminal error; retry or hand off")
        return code
    return tracked


def command(args) -> int:
    if args.action == "report":
        try:
            card = publish({key: getattr(args, key) for key in
                            ("seat", "project", "state", *FIELDS)})
        except ValueError as exc:
            print(f"[megazword] {exc}")
            return 2
        print(f"Saved report for {card['seat']}.")
    else:
        print(render(snapshot()))
    return 0
