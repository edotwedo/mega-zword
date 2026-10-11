"""Reset-aware plan pacing and service ranking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .usage_sources import PlanUsage, Window

WINDOW_LENGTHS = {
    "5-hour": timedelta(hours=5),
    "weekly": timedelta(days=7),
}
HARD_ONLY_THRESHOLD = 10.0
OUT_THRESHOLD = 95.0


@dataclass
class PlanStatus:
    service: str
    worst_pace: float
    max_used_percent: float
    verdict: str
    unknown_windows: list[str]


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
    paces = [pace(window, now) for window in usage.windows]
    maximum = max(float(window.used_percent) for window in usage.windows)
    unknown = [window.name for window in usage.windows
               if not window_length(window.name)[1]]
    if maximum >= OUT_THRESHOLD:
        verdict = "out"
    elif max(paces) > HARD_ONLY_THRESHOLD:
        verdict = "hard-only"
    else:
        verdict = "free"
    return PlanStatus(usage.service, max(paces), maximum, verdict, unknown)


def allowed(service_status: PlanStatus, rating: str) -> bool:
    """Return whether this service may take a task of the given rating."""
    if service_status.verdict == "out":
        return False
    if service_status.verdict == "hard-only":
        return rating == "hard"
    return service_status.verdict in {"free", "unknown"}


def rank(statuses: dict[str, PlanStatus], candidates: list[str], rating: str,
         now: datetime | None = None) -> list[str]:
    """Filter candidates and rank by usage left to burn before reset."""
    del now  # Statuses are computed with their own explicit reference time.
    eligible = [name for name in candidates
                if name in statuses and allowed(statuses[name], rating)]
    order = {name: index for index, name in enumerate(candidates)}
    return sorted(
        eligible,
        key=lambda name: (
            statuses[name].verdict == "unknown",
            statuses[name].worst_pace,
            order[name],
        ),
    )
