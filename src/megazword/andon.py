"""The andon cord: one switch that stops every agent job before its next step.

A shop-floor andon stops the line for everyone, and nothing on it is thrown away.
`megazword night stop` stops the night shift; this stops the agent loop itself,
wherever it is running, and leaves every edit in the work folder. Pulling it is
cheap and instant, which is the point - the person who spots the problem is
rarely the person who owns the job.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import config
from .filelock import write_atomic

FLAG_NAME = "ANDON"


def flag_path() -> Path:
    return config.HOME / FLAG_NAME


def is_on() -> bool:
    return flag_path().exists()


def note(path: Path | None = None) -> str:
    """What the puller wrote, or "" when the cord was pulled without a reason.

    The file's first line is the timestamp, so it answers "when" without the
    reason ever reading as a date.
    """
    try:
        text = (path or flag_path()).read_text(encoding="utf-8")
    except OSError:
        return ""
    return " ".join(text.splitlines()[1:]).strip()


def pull(reason: str = "", path: Path | None = None) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    target = path or flag_path()
    write_atomic(target, f"{stamp}\n{reason.strip()}\n" if reason.strip() else f"{stamp}\n")
    return target


def release(path: Path | None = None) -> bool:
    """False when it was already off, so the command can say so instead of lying."""
    try:
        (path or flag_path()).unlink()
        return True
    except FileNotFoundError:
        return False


def stop_message() -> str:
    why = note()
    return ("andon is pulled: work is paused"
            + (f" ({why})" if why else "")
            + "; edits remain in the work folder. Clear it with `megazword andon off`")


def status_line() -> str:
    if not is_on():
        return "andon off: jobs run"
    why = note()
    return "andon ON: jobs stop before their next step" + (f" - {why}" if why else "")


def command(state: str | None, write: Callable[[str], None] = print) -> int:
    if state == "on":
        pull()
        write(status_line())
        return 0
    if state == "off":
        write("andon released: jobs run again" if release() else "andon was already off")
        return 0
    write(status_line())
    return 0


def add_parser(sub) -> None:
    andon = sub.add_parser("andon", help="pull the cord: stop every agent job before its next step")
    andon.add_argument("state", nargs="?", choices=("on", "off"),
                       help="on pauses every job, off releases them; bare shows the state")
