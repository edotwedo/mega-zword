"""A local andon cord, checked once before each agent step."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Callable

from . import config
from .filelock import write_atomic


class Paused(RuntimeError):
    """An intentional stop, outside the agent's failure window."""


def flag_path():
    return config.HOME / "ANDON"


def is_on() -> bool:
    return flag_path().exists()


def details() -> dict:
    try:
        return json.loads(flag_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def pull(reason=""):
    data = {"reason": reason.strip(), "who": os.environ.get("MEGAZWORD_SEAT") or "unknown",
            "time": datetime.now(timezone.utc).isoformat()}
    write_atomic(flag_path(), json.dumps(data))
    return data


def release():
    flag_path().unlink(missing_ok=True)


def status_line():
    if not is_on():
        return "andon off: jobs run"
    data = details()
    return (f"andon ON: {data.get('reason', '')} "
            f"(by {data.get('who', 'unknown')} at {data.get('time', 'unknown')})")


def command(state: str | None, reason="", write: Callable[[str], None] = print) -> int:
    seat = os.environ.get("MEGAZWORD_SEAT") or "unknown"
    if state == "on":
        data = pull(reason)
        line = f"{seat}: ANDON on - {data['reason']}. All jobs pause at their next step."
    elif state == "off":
        release()
        line = f"{seat}: ANDON off"
    else:
        write(status_line())
        return 0
    write(status_line())
    try:
        from .room import say
        say("hive", line, author="floor", write=lambda _: None)
    except Exception:
        pass  # The local switch must work even when the room is unavailable.
    return 0


def add_parser(sub):
    parser = sub.add_parser("andon", help="pause all agent jobs before their next step")
    parser.add_argument("state", nargs="?", choices=("on", "off"))
    parser.add_argument("reason", nargs="*", help="why the jobs should pause")
