"""Reset-aware plan pacing and service ranking."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

from .usage_sources import PlanUsage, Window

WINDOW_LENGTHS = {
    "5-hour": timedelta(hours=5),
    "weekly": timedelta(days=7),
}
HARD_ONLY_THRESHOLD = 10.0
OUT_THRESHOLD = 95.0
# "Use it or lose it": a window this close to its reset with at least
# LEFTOVER_MIN percent unused gets spent first, even on easy tasks.
BURN_BEFORE_RESET = {"5-hour": timedelta(hours=1), "weekly": timedelta(hours=24)}
LEFTOVER_MIN = 20.0


@dataclass
class PlanStatus:
    service: str
    worst_pace: float
    max_used_percent: float
    verdict: str
    unknown_windows: list[str]
    burn: bool = False  # near a reset with usage left over: spend it now


def window_length(name: str) -> tuple[timedelta, bool]:
    """Return the window duration and whether its name is recognized."""
    if name == "5-hour":
        return WINDOW_LENGTHS["5-hour"], True
    if name == "weekly" or name.startswith("weekly"):
        return WINDOW_LENGTHS["weekly"], True
    return timedelta(days=7), False


def pace(window: Window, now: datetime | None = None) -> float:
    """Return percentage points ahead of expected usage for this window."""
    now = now or datetime.now(timezone.utc)
    if window.resets_at is None:
        return 0.0
    reset = window.resets_at
    if reset.tzinfo is None:
        reset = reset.replace(tzinfo=timezone.utc)
    length, _ = window_length(window.name)
    elapsed = (now - (reset - length)).total_seconds() / length.total_seconds()
    elapsed_percent = min(100.0, max(0.0, elapsed * 100.0))
    return float(window.used_percent) - elapsed_percent


def status(usage: PlanUsage, now: datetime | None = None) -> PlanStatus:
    """Summarize the most restrictive usage window for a service."""
    if not usage.windows:
        return PlanStatus(usage.service, 0.0, 0.0, "unknown", [])
    # Unrecognized windows (e.g. Claude's "iguana_necktie", which Phil says is
    # his Claude Cloud credit) are reported but never block a plan.
    known = [_after_reset(w, now) for w in usage.windows if window_length(w.name)[1]]
    unknown = [w.name for w in usage.windows if not window_length(w.name)[1]]
    if not known:
        return PlanStatus(usage.service, 0.0, 0.0, "unknown", unknown)
    paces = [pace(window, now) for window in known]
    maximum = max(float(window.used_percent) for window in known)
    if maximum >= OUT_THRESHOLD:
        verdict = "out"
    elif max(paces) > HARD_ONLY_THRESHOLD:
        verdict = "hard-only"
    else:
        verdict = "free"
    return PlanStatus(usage.service, max(paces), maximum, verdict, unknown,
                      burn=verdict == "free" and any(_near_reset(w, now) for w in known))


def _aware(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _after_reset(window: Window, now: datetime | None = None) -> Window:
    """A reading taken before its window reset says nothing about the new window: count it
    as unused, so a stale '100%, resets Sun 3:57 PM' stops blocking the AI once Sunday 3:57 passes."""
    now = now or datetime.now(timezone.utc)
    if window.resets_at is not None and _aware(window.resets_at) < now:
        return replace(window, used_percent=0.0, resets_at=None)
    return window


def _near_reset(window: Window, now: datetime | None = None) -> bool:
    if window.resets_at is None or 100.0 - window.used_percent < LEFTOVER_MIN:
        return False
    now = now or datetime.now(timezone.utc)
    reset = _aware(window.resets_at)
    key = "5-hour" if window.name == "5-hour" else "weekly"
    return timedelta(0) <= reset - now <= BURN_BEFORE_RESET[key]


def allowed(service_status: PlanStatus, rating: str) -> bool:
    """Return whether this service may take a task of the given rating."""
    if service_status.verdict == "out":
        return False
    if service_status.verdict == "hard-only":
        return rating == "hard"
    return service_status.verdict in {"free", "unknown"}


def rank(statuses: dict[str, PlanStatus], candidates: list[str], rating: str,
         now: datetime | None = None) -> list[str]:
    """Drop AIs that are out or over pace, then keep the route's order
    (cheapest first), except plans about to reset with usage left go first."""
    del now  # Statuses are computed with their own explicit reference time.
    # AIs with no meter at all (grok, local models) count as "unknown".
    statuses = {name: statuses.get(name) or PlanStatus(name, 0.0, 0.0, "unknown", [])
                for name in candidates}
    eligible = [name for name in candidates if allowed(statuses[name], rating)]
    order = {name: index for index, name in enumerate(candidates)}
    return sorted(
        eligible,
        key=lambda name: (not statuses[name].burn, order[name]),
    )
