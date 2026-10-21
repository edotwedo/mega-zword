"""Wake the conductor when Phil posts, with no model call while idle.

Phil could not reach the hive from work on 2026-10-21: nothing he could use there woke a PC
seat, his messages sat unanswered, and the conductor's own beats were reading a stale local
cache. This closes that gap. It polls the room, and when a Phil lane posts - or a web lane
says it is relaying Phil - it produces one short line that a watcher types into the
conductor's tab, so that seat's next turn starts immediately instead of at the next beat.

Cost while idle: one HTTP GET per interval, zero model calls. It never reads message text
back into a prompt beyond the count, so a hostile room message cannot become an instruction.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Callable

from . import config

# Phil's lanes. A message from here always wakes the conductor.
PHIL_LANES = ("phil", "phone", "grok-web")
# A web lane may only wake when it names Phil as the source; on its own it is teammate data.
WEB_LANES = ("claude-web", "chatgpt", "gemini-web")
RELAY = re.compile(r"\b(relay|relaying|from phil|phil (?:says|asks|wants|directly))\b", re.IGNORECASE)


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


def is_wake(text: str, author: str) -> bool:
    """Whether this message should start the conductor's turn."""
    lane = (author or "").strip().lower()
    if lane in PHIL_LANES:
        return True
    if lane in WEB_LANES:
        return bool(RELAY.search(text or ""))
    return False


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


def last_seen(home: Path | None = None) -> int:
    try:
        return int(json.loads(state_path(home).read_text(encoding="utf-8")).get("seen", 0))
    except (OSError, ValueError, TypeError):
        return 0


def remember(identifier: int, home: Path | None = None) -> None:
    path = state_path(home)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"seen": int(identifier)}) + "\n", encoding="utf-8")
    except OSError:
        pass


def most_recent_id(messages) -> int:
    best = 0
    for message in messages:
        best = max(best, _identifier(message))
    return best


def once(*, home: Path | None = None, read: Callable | None = None,
         write: Callable[[str], None] = print) -> int:
    """One poll. Prints a wake line and advances the cursor when Phil is waiting.

    Returning 0 with no output is the normal idle case: no model call, no noise.
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
    seen = last_seen(home)
    waiting = pending(messages, seen)
    newest = most_recent_id(messages)
    if waiting:
        write(wake_line(waiting))
        remember(newest or seen, home)
        return 0
    if newest > seen:
        remember(newest, home)  # nothing for the conductor, but do not re-scan next time
    return 0


def add_parser(sub) -> None:
    wake = sub.add_parser(
        "wake",
        help="poll the room once and print a wake line if Phil is waiting; no AI calls",
    )
    wake.add_argument("--home", type=Path, help="megazword home (default: ~/.megazword)")


def command(args) -> int:
    return once(home=getattr(args, "home", None))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--home", type=Path)
    return command(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
