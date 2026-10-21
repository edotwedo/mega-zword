"""Spot warning: the 2026-10-21 reserve, one rule per window.

Five-hour window: at 10% remaining, stop and hand off until the reset.
Weekly window: at 10% remaining, keep working, and hard-stop at 5%.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from . import config

FIVE_HOUR_STOP = 10  # percent remaining: hand off until the 5-hour reset
WEEKLY_KEEP = 10     # percent remaining: still take work
WEEKLY_STOP = 5      # percent remaining: hard stop


def remaining(usage) -> float:
    """Percent left in the tightest *recognized* window of one plan.

    Unknown buckets (e.g. Claude's `iguana_necktie`) never block pacing, so they
    must not make spot report 0% left.
    """
    windows = [w for w in (getattr(usage, "windows", []) or [])
               if getattr(w, "name", "") in ("5-hour", "weekly")]
    used = max((float(getattr(w, "used_percent", 0.0) or 0.0) for w in windows), default=0.0)
    return max(0.0, 100.0 - used)


def _window_line(service: str, name: str, used: float) -> str | None:
    left = max(0.0, 100.0 - float(used or 0.0))
    if name == "5-hour":
        if left <= FIVE_HOUR_STOP:
            return f"{service}: 5-hour {left:.0f}% left - STOP (hand off until reset)"
        return None
    if name == "weekly" or str(name).startswith("weekly"):
        if left <= WEEKLY_STOP:
            return f"{service}: weekly {left:.0f}% left - STOP (at floor)"
        if left <= WEEKLY_KEEP:
            return f"{service}: weekly {left:.0f}% left - KEEP WORKING (down to 5%)"
    return None


def warnings(usages) -> list[str]:
    lines = []
    for usage in usages:
        for window in getattr(usage, "windows", []) or []:
            name = getattr(window, "name", "")
            if name not in ("5-hour", "weekly") and not str(name).startswith("weekly"):
                continue
            line = _window_line(usage.service, name, getattr(window, "used_percent", 0.0))
            if line:
                lines.append(line)
    return lines


def command(args=None, write=print) -> int:
    from .usage_sources import all_usage
    try:
        usages = all_usage(config.HOME / "log.jsonl")
    except (OSError, ValueError) as exc:
        write(f"[spot] usage unavailable: {exc}")
        return 2
    lines = warnings(usages)
    if not lines:
        write("[spot] every recognized window is above its reserve")
        return 0
    for line in lines:
        write(line)
    path = config.HOME / "spot-handoff.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "time": datetime.now(timezone.utc).isoformat(),
        "warnings": lines,
    }, indent=2), encoding="utf-8")
    write(f"[spot] wrote {path}")
    return 0
