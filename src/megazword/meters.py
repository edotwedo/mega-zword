"""One summary per plan, shared by the start screen, `megazword usage` and
the dashboard, so they never disagree about an AI.

Order of truth: marked out (config [out]) beats any meter; then the worst
known window; snapshots older than STALE are flagged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from textwrap import shorten

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
    windows: tuple[tuple[str, float], ...] = ()

    def line(self) -> str:
        """One plain line (no colour), e.g. 'codex   out until Sun Oct 11 02:45 AM'."""
        if self.state == "out":
            text = f"out until {self.out_until.astimezone():%a %b %d %I:%M %p}"
        elif self.state == "meter":
            # Lead with what's left: "2% 5-hour" read as 2% remaining (Phil, 2026-10-17).
            left = f"{max(0, 100 - self.used):.0f}% left"
            if len(self.windows) > 1:
                text = left + " (" + ", ".join(f"{name} {used:.0f}% used" for name, used in self.windows) + ")"
            else:
                filled = max(0, min(10, round(self.used / 10)))
                text = f"[{'#' * filled}{'.' * (10 - filled)}] {left} ({self.window} {self.used:.0f}% used)"
        else:
            text = shorten(self.note or "no meter", width=60, placeholder="...")
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
                       as_of=as_of, stale=stale,
                       windows=tuple((w.name, w.used_percent) for w in known))
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


def labor_order(summaries: list[Summary]) -> list[tuple[str, str]]:
    """Rank AIs for new work by spare usage right now: most room first, unknown
    meters next, out AIs last. Returns (service, reason) pairs. It is a reading,
    not a rule: re-run it before each piece of work."""
    def key(s: Summary):
        if s.state == "out":
            return (2, 0.0)
        if s.state == "meter":
            return (0, s.used or 0.0)
        return (1, 0.0)
    out = []
    for s in sorted(summaries, key=key):
        if s.state == "out":
            reason = f"out until {s.out_until.astimezone():%a %I:%M %p}; skip"
        elif s.state == "meter":
            reason = f"{100 - (s.used or 0):.0f}% left in its {s.window} window"
            if s.stale:
                reason += " (old reading)"
        else:
            reason = "no meter; check by hand"
        out.append((s.service, reason))
    return out
