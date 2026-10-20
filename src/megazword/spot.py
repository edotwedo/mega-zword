"""Spot warning: tell a seat to hand off before a plan hits the 20% floor."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from . import config

FLOOR = 20  # hard floor: never start heavy work below this
WARN = 25   # hand off before spending the last slice


def remaining(usage) -> float:
    """Percent left in the tightest *recognized* window of one plan.

    Unknown buckets (e.g. Claude's `iguana_necktie`) never block pacing, so they
    must not make spot report 0% left.
    """
    windows = [w for w in (getattr(usage, "windows", []) or [])
               if getattr(w, "name", "") in ("5-hour", "weekly")]
    used = max((float(getattr(w, "used_percent", 0.0) or 0.0) for w in windows), default=0.0)
    return max(0.0, 100.0 - used)


def warnings(usages) -> list[str]:
    lines = []
    for usage in usages:
        left = remaining(usage)
        if left <= WARN:
            state = "STOP (at floor)" if left <= FLOOR else "HAND OFF SOON"
            lines.append(f"{usage.service}: {left:.0f}% left - {state}")
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
        write(f"[spot] every AI is above the {WARN}% warn line")
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
