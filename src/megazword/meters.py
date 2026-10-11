"""One summary per plan, shared by the start screen, `megazword usage` and
the dashboard, so they never disagree about an AI.

Order of truth: marked out (config [out]) beats any meter; then the worst
known window; snapshots older than STALE are flagged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .pacing import window_length
from .usage_sources import PlanUsage

STALE = timedelta(hours=1)


@dataclass
class Summary:
    service: str
    state: str                     # "out" | "meter" | "none"
    used: float | None = None      # worst known window, percent
    window: str = ""               # its name, e.g. "5-hour"
    out_until: datetime | None = None
    as_of: datetime | None = None  # None = read just now
    stale: bool = False
    note: str = ""

    def line(self) -> str:
        """One plain line (no colour), e.g. 'codex   out until Sun Oct 11 02:45 AM'."""
        if self.state == "out":
            text = f"out until {self.out_until.astimezone():%a %b %d %I:%M %p}"
        elif self.state == "meter":
            filled = max(0, min(10, round(self.used / 10)))
            text = f"[{'#' * filled}{'.' * (10 - filled)}] {self.used:3.0f}% {self.window}"
        else:
            text = (self.note or "no meter")[:60]
        if self.as_of and self.state != "out":
            text += f"  (as of {self.as_of.astimezone():%I:%M %p}{', stale' if self.stale else ''})"
        return f"{self.service:7} {text}"


def summarize(plan: PlanUsage, out_until: dict[str, datetime],
              now: datetime | None = None) -> Summary:
    now = now or datetime.now(timezone.utc)
    as_of = plan.as_of
    stale = bool(as_of and now - as_of > STALE)
    until = out_until.get(plan.service)
    if until and until > now:
        return Summary(plan.service, "out", out_until=until, as_of=as_of, stale=stale)
    known = [w for w in plan.windows if window_length(w.name)[1]]
    if known:
        worst = max(known, key=lambda w: w.used_percent)
        return Summary(plan.service, "meter", worst.used_percent, worst.name,
                       as_of=as_of, stale=stale)
    return Summary(plan.service, "none", note=plan.note if not plan.windows else "no meter",
                   as_of=as_of, stale=stale)


def summarize_all(plans: list[PlanUsage], out_until: dict[str, datetime],
                  now: datetime | None = None) -> list[Summary]:
    found = [summarize(p, out_until, now) for p in plans]
    now = now or datetime.now(timezone.utc)
    seen = {s.service for s in found}
    # An AI can be marked out without having a meter at all (e.g. by hand).
    for name, until in sorted(out_until.items()):
        if name not in seen and until > now:
            found.append(Summary(name, "out", out_until=until))
    return found
