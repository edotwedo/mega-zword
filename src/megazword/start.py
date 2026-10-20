"""What plain `megazword` shows: plans, who's out, recent runs, top commands."""

from __future__ import annotations

import sys
import threading
from textwrap import shorten
from datetime import datetime, timezone

from . import config, runlog

METER_WAIT = 2.0  # never hold the screen longer than this for the meters

COMMANDS = [
    ('run "..."', "ask; Mega Zword picks the AI (add -m claude to choose)"),
    ("chat", "back-and-forth conversation, /help for commands"),
    ("dashboard --app", "the app window: meters, runs, run box"),
    ('run --compare a,b "..."', "same question to 2-3 AIs side by side"),
    ("usage  /  stats", "plan meters now  /  per-day numbers"),
    ("doctor", "check that everything is set up right"),
]


def _meters(source=None, wait: float = METER_WAIT) -> list | None:
    """Plan meters, or None if they didn't arrive within `wait` seconds."""
    from .usage_sources import all_usage
    box: list = []

    def read() -> None:
        try:
            box.append((source or all_usage)())
        except Exception:
            box.append([])
    t = threading.Thread(target=read, daemon=True)
    t.start()
    t.join(wait)
    return box[0] if box else None


def _ago(stamp: str, now: datetime) -> str:
    try:
        t = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return "?"
    s = (now - (t if t.tzinfo else t.replace(tzinfo=timezone.utc))).total_seconds()
    return "now" if s < 60 else f"{int(s // 60)}m ago" if s < 3600 else \
        f"{int(s // 3600)}h ago" if s < 86400 else f"{int(s // 86400)}d ago"


def render(cfg: config.Config, meters=None, now: datetime | None = None,
           color: bool | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    color = sys.stdout.isatty() if color is None else color
    bold = (lambda s: f"\033[1m{s}\033[0m") if color else (lambda s: s)
    dim = (lambda s: f"\033[2m{s}\033[0m") if color else (lambda s: s)
    from . import __version__
    lines = [bold(f"Mega Zword {__version__}") + dim("  -  one place for all your AIs"), ""]
    if cfg.work_owner:
        lines += [f"Work owner: {cfg.work_owner} (capacity rankings choose support, not ownership)", ""]

    from .meters import summarize_all
    plans = _meters() if meters is None else meters
    if plans is None:
        lines.append("Plans:  meters still loading (try `megazword usage`)")
        if cfg.out_now(now):  # still say who's out; that needs no meter
            plans = []
    else:
        lines.append("Plans:")
    if plans is not None:
        summaries = summarize_all(plans, cfg.out_until, now)
        for summary in summaries[:6]:
            line = summary.line()
            lines.append("  " + (line if len(line) <= 78 else
                                  shorten(line, width=78, placeholder="...")))
        if len(summaries) > 6:
            lines.append(f"  {len(summaries) - 6} more plans: megazword usage")

    recent = runlog.read(cfg.log_path)[-3:]
    lines += ["", "Last runs:" if recent else "Last runs: none yet"]
    for r in reversed(recent):
        result = "ok" if r.get("ok") else "failed"
        lines.append(f"  {_ago(str(r['time']), now):7} {r['backend']:7} {result}")

    lines += ["", "Try:"]
    for cmd, what in COMMANDS:
        prefix = f"  megazword {cmd:24} "
        lines.append(prefix + dim(shorten(what, width=80 - len(prefix), placeholder="...")))
    lines.append(dim("  megazword --help for everything else"))
    return "\n".join(lines)
