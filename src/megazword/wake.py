"""Wake the conductor when Phil posts, with no model call while idle.

Phil could not reach the hive from work on 2026-10-21: nothing he could use there woke a PC
seat, his messages sat unanswered, and the conductor's own beats were reading a stale local
cache. This closes that gap. It polls the room, and when a message matters to this seat - it
is from a Phil lane, names the seat, touches an item the seat holds, or is addressed to the
floor - it produces one short line that a watcher types into the conductor's tab, so that
seat's next turn starts immediately instead of at the next beat. Everything else is counted,
not answered: a seat that takes every message is noise, and a seat that takes none looks dead.

Cost while idle: one HTTP GET per interval, zero model calls. It never reads message text
back into a prompt beyond the count, so a hostile room message cannot become an instruction.
Every poll leaves a monotonic tick in wake.json, so `wake --health` reports a number instead
of the word "Ready" - a listener that died and one with nothing to say are otherwise alike.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import claims as ledger
from . import config
from .filelock import locked, write_atomic
from .room import is_phil

# The watcher polls every 60 s (scripts/wake_watch.ps1). Three missed polls means the
# listener is down, not quiet.
HEALTH_MAX = 180.0
# One digest an hour: often enough to prove the seat is alive, rare enough to stay quiet.
DIGEST_SECONDS = 3600
# A roll call or an announcement: addressed to the floor, so every seat reads it.
BROADCAST = re.compile(r"broadcast\s*:|\bevery\s+seat\b|\ball\s+seats\b|\broll[\s-]?call\b", re.IGNORECASE)
# An action on an item I hold: someone landing, releasing or taking it is my business.
# Word-level, not anchored, because a "<Designation>: ..." prefix leads the line.
ITEM_WORK = re.compile(
    r"\b(claim\w*|tak(?:e|es|en|ing)|reserv\w*|grab\w*|own\w*|assign\w*|reassign\w*|"
    r"releas\w*|drop\w*|land\w*|merg\w*|shipp?\w*|push(?:ed|ing)?|fix(?:ed|ing)?|"
    r"done|finished|complete\w*)\b",
    re.IGNORECASE,
)


def _field(message, name, default=""):
    return message.get(name, default) if isinstance(message, dict) else getattr(message, name, default)


def _identifier(message) -> int:
    """The room id. Cached messages carry it as `remote_id`; live ones as `id`.

    The first version read only `id`, so every cached message looked like id 0, nothing was
    ever "newer than the cursor", and the listener could not wake on anything. The live run
    is what exposed it.
    """
    for name in ("id", "remote_id"):
        try:
            value = int(_field(message, name) or 0)
        except (TypeError, ValueError):
            continue
        if value:
            return value
    return 0


def _squash(text) -> str:
    """Lowercase and drop separators, so `Cinder-21`, `cinder 21` and `cinder21` are one."""
    return re.sub(r"[\s_\-]+", "", str(text or "").casefold())


def _assigned_to(text, me) -> bool:
    """True when the line opens `<me>:` - the designation form every room post uses.

    The trailing "(claude-pc)" many seats carry is dropped: `Cinder-21 (pc): go` addresses
    Cinder-21.
    """
    head = str(text or "").strip()
    if not head:
        return False
    head = head.splitlines()[0]
    if ":" not in head:
        return False
    designation = re.sub(r"\([^)]*\)", "", head.split(":", 1)[0])
    seat = _squash(me)
    return bool(seat) and _squash(designation) == seat


def _my_item(text, claimed) -> bool:
    """True when the line names an item this seat holds and says work happened on it.

    Item semantics (numbers vs. a quoted name) are claims.py's, not re-invented here.
    """
    if not claimed:
        return False
    for item in claimed:
        keys = ledger.item_keys(str(item))
        if keys and ledger.mentions(text, keys) and ITEM_WORK.search(text or ""):
            return True
    return False


def relevance(message, me, claims=()) -> str | None:
    """Why this message matters to seat `me`, or None when it is someone else's business.

    A seat polling every minute sees mostly other seats' work. Answering all of it is noise;
    answering none of it looks dead. This decides per message, and the poll counts what it
    let pass. Ambiguity falls towards waking: one needless answer is cheaper than one missed
    assignment.
    """
    text = _field(message, "text") or ""
    author = (_field(message, "author") or "").strip().lower()
    if is_phil(author):
        return "phil"
    seat = _squash(me)
    if seat and seat in _squash(text):
        return "mention"
    if _assigned_to(text, me):
        return "assigned"
    if _my_item(text, claims):
        return "my-item"
    if BROADCAST.search(text):
        return "broadcast"
    return None


def is_wake(text: str, author: str) -> bool:
    """Whether this message should start the conductor's turn.

    One question now: would the relevance filter wake this seat? `me` comes from the
    environment, since the watcher runs as the seat it serves.
    """
    return relevance({"text": text, "author": author},
                     os.environ.get("MEGAZWORD_SEAT")) is not None


def pending(messages, since_id: int = 0) -> list:
    """Messages newer than since_id that should wake the conductor, oldest first."""
    found = []
    for message in messages:
        if _identifier(message) <= since_id:
            continue
        if is_wake(_field(message, "text"), _field(message, "author")):
            found.append(message)
    return found


def wake_line(messages) -> str:
    """One line, safe to type into a terminal: no message text, no quotes, no newlines."""
    if not messages:
        return ""
    more = f" (+{len(messages) - 1} more)" if len(messages) > 1 else ""
    return f"Cinder-21: Phil posted in the hive{more} - read the room and answer now."


def state_path(home: Path | None = None) -> Path:
    return (home or config.HOME) / "wake.json"


def _state(home: Path | None = None) -> dict:
    """The whole wake.json as a dict; anything unreadable is treated as empty."""
    try:
        data = json.loads(state_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _whole(value) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, number)


def last_seen(home: Path | None = None) -> int:
    return _whole(_state(home).get("seen", 0))


def _save(fields: dict, home: Path | None = None) -> None:
    """Merge fields into wake.json under the sidecar lock.

    Three writers share this one file now - the cursor, the tick and the quiet count - so a
    whole-file rewrite would make them clobber one another.
    """
    path = state_path(home)
    with locked(path) as acquired:
        if not acquired:
            raise OSError("wake state is locked; state was not saved")
        state = _state(home)
        state.update(fields)
        write_atomic(path, json.dumps(state) + "\n")


def remember(identifier: int, home: Path | None = None) -> None:
    if identifier < 0:
        raise ValueError("wake acknowledgement must be nonnegative")
    _save({"seen": max(last_seen(home), int(identifier))}, home)


ack = remember


def _as_utc(now: datetime | None = None) -> datetime:
    """An aware UTC datetime; a naive one is read as UTC (the room's clock)."""
    when = now or datetime.now(timezone.utc)
    return when.astimezone(timezone.utc) if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _stamp(now: datetime) -> str:
    return _as_utc(now).isoformat(timespec="seconds")


def _parse_time(value) -> datetime | None:
    """ISO text from wake.json as an aware datetime, or None when it is unusable."""
    if not value:
        return None
    try:
        when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def most_recent_id(messages) -> int:
    best = 0
    for message in messages:
        best = max(best, _identifier(message))
    return best


def tick_age(home: Path | None = None, now: datetime | None = None) -> float | None:
    """Seconds since the last poll, or None when no poll has been recorded.

    A listener that stopped and one with nothing to say look the same in the room, so every
    poll leaves a tick with its timestamp and `wake --health` reads that number.
    """
    when = _parse_time(_state(home).get("at"))
    if when is None:
        return None
    return (_as_utc(now) - when).total_seconds()


def health(home: Path | None = None, now: datetime | None = None,
           write: Callable[[str], None] = print) -> int:
    """Print the tick and its age; exit 1 when the last poll is older than 3 intervals.

    "Ready" is not a measurement. A watcher that died between intervals and one that simply
    had nothing to deliver both print nothing, so health reads the tick instead.
    """
    age = tick_age(home, now)
    tick = _whole(_state(home).get("tick", 0))
    if age is None:
        write("tick 0, age unknown")
        return 1
    write(f"tick {tick}, age {int(age)}s")
    return 1 if age > HEALTH_MAX else 0


def _digest(state: dict, now: datetime | None = None) -> str | None:
    """Mutate a state dict: return the hourly quiet line and reset, or return None."""
    count = _whole(state.get("suppressed", 0))
    at = _as_utc(now)
    last = _parse_time(state.get("digest_at"))
    if count <= 0 or (last is not None and (at - last).total_seconds() < DIGEST_SECONDS):
        return None
    state["suppressed"] = 0
    state["digest_at"] = _stamp(at)
    return f"hive: {count} messages, none for you"


def digest(state, now: datetime | None = None) -> str | None:
    """One hourly line for the messages this seat let pass, or None.

    A seat that only ever hears others must still prove it is listening. Passing `home`
    reads and updates wake.json in place; a dict is updated by the caller.
    """
    if isinstance(state, dict):
        return _digest(state, now)
    home = state
    loaded = _state(home)
    line = _digest(loaded, now)
    if line:
        _save({"suppressed": loaded.get("suppressed", 0), "digest_at": loaded.get("digest_at")}, home)
    return line


def once(*, home: Path | None = None, read: Callable | None = None,
         write: Callable[[str], None] = print, peek: bool = False,
         as_json: bool = False, me: str | None = None, claims=()) -> int:
    """One poll. Prints a wake line when the room has something for this seat.

    Returning 0 with no output is the normal idle case: no model call, no noise. Every poll
    still records the highest room id it saw and when, and counts what it let pass towards
    the next digest, so a silent seat is visibly alive rather than seemingly dead.
    """
    if read is None:
        from . import room
        def read():
            # claim_messages refreshes from the Worker; read_messages would read the local
            # cache, which is the bug that hid Phil's messages for three hours.
            return room.claim_messages("hive", config.load(), home)
    try:
        messages = list(read())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        write(f"[megazword wake] room unreadable ({type(exc).__name__}); no wake sent")
        return 1
    seat = me if me is not None else (os.environ.get("MEGAZWORD_SEAT") or None)
    seen = last_seen(home)
    fresh = [m for m in messages if _identifier(m) > seen]
    waiting = [m for m in fresh if relevance(m, seat, claims) is not None]
    quiet = len(fresh) - len(waiting)
    newest = most_recent_id(messages)
    fields = {"tick": newest, "at": _stamp(_as_utc())}
    if waiting:
        line = wake_line(waiting)
        write(json.dumps({"through": newest or seen, "line": line}) if as_json else line)
        if not peek:
            fields["seen"] = max(seen, newest or seen)
    elif newest > seen and not peek:
        fields["seen"] = newest  # nothing for the conductor, but do not re-scan next time
    # Only count when the cursor advances: the watcher polls with --peek, and counting the
    # same backlog every interval would inflate the digest without bound.
    if quiet and not peek:
        fields["suppressed"] = _whole(_state(home).get("suppressed", 0)) + quiet
    _save(fields, home)
    return 0


def add_parser(sub) -> None:
    wake = sub.add_parser(
        "wake",
        help="poll the room once and print a wake line if Phil is waiting; no AI calls",
    )
    wake.add_argument("--home", type=Path, help="megazword home (default: ~/.megazword)")
    wake.add_argument("--peek", action="store_true", help="leave messages pending until acknowledged")
    wake.add_argument("--json", action="store_true", help="print a wake line and captured cursor as JSON")
    wake.add_argument("--ack", type=int, help="acknowledge through this captured message id after delivery")
    wake.add_argument("--digest", action="store_true", help="print the hourly quiet-room count, if due")
    wake.add_argument("--health", action="store_true", help="print the poll tick and age; exit 1 when stale")


def command(args) -> int:
    home = getattr(args, "home", None)
    try:
        if getattr(args, "digest", False):
            line = digest(home)
            if line:
                print(line)
            return 0
        if getattr(args, "health", False):
            return health(home)
        if getattr(args, "ack", None) is not None:
            remember(args.ack, home)
            return 0
        return once(home=home, peek=getattr(args, "peek", False),
                    as_json=getattr(args, "json", False))
    except (OSError, ValueError) as exc:
        print(f"[megazword wake] state not saved ({type(exc).__name__})", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--home", type=Path)
    parser.add_argument("--peek", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--ack", type=int)
    parser.add_argument("--digest", action="store_true")
    parser.add_argument("--health", action="store_true")
    return command(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
