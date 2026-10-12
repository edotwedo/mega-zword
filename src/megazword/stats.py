"""Per-day, per-AI statistics from the run log (`megazword stats`)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import runlog


@dataclass
class DayStat:
    day: str          # YYYY-MM-DD, local time
    backend: str
    runs: int = 0
    ok: int = 0
    moved_on: int = 0  # rejected or failed: Mega Zword had to try another AI
    seconds: float = 0.0
    est_tokens: int = 0

    @property
    def ok_rate(self) -> float:
        return self.ok / self.runs if self.runs else 0.0

    @property
    def escalation_rate(self) -> float:
        return self.moved_on / self.runs if self.runs else 0.0

    @property
    def avg_seconds(self) -> float:
        return self.seconds / self.runs if self.runs else 0.0


def _local_day(stamp: str) -> date | None:
    try:
        t = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone().date()


def daily(path: Path, days: int = 7, today: date | None = None) -> list[DayStat]:
    """Stats for the last `days` days (today included), oldest first."""
    today = today or datetime.now().astimezone().date()
    first = today - timedelta(days=days - 1)
    found: dict[tuple[str, str], DayStat] = {}
    for r in runlog.read(path):
        day = _local_day(r["time"])
        if day is None or not first <= day <= today:
            continue
        key = (day.isoformat(), str(r["backend"]))
        s = found.setdefault(key, DayStat(*key))
        s.runs += 1
        s.ok += bool(r.get("ok"))
        s.moved_on += not r.get("ok")
        s.seconds += runlog._number(r.get("seconds"))  # bad values count as 0, never crash
        s.est_tokens += int(runlog._number(r.get("est_tokens")))
    return sorted(found.values(), key=lambda s: (s.day, s.backend))


def trend(path: Path, days: int = 7, today: date | None = None) -> list[dict]:
    """One entry per day (gaps filled with zeros) for the dashboard chart."""
    today = today or datetime.now().astimezone().date()
    stats = daily(path, days, today)
    out = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        out.append({"day": d, "runs": {s.backend: s.runs for s in stats if s.day == d},
                    "ok": {s.backend: s.ok for s in stats if s.day == d}})
    return out


def table(stats: list[DayStat]) -> str:
    """Compact table that fits a phone-width terminal."""
    if not stats:
        return "[megazword] no runs in this period"
    rows = ["day    AI      runs  ok%  avg s  esc%  tokens"]
    for s in stats:
        rows.append(f"{s.day[5:]:6} {s.backend:7} {s.runs:4} {s.ok_rate * 100:4.0f} "
                    f"{s.avg_seconds:6.1f} {s.escalation_rate * 100:5.0f} {s.est_tokens:7}")
    totals: dict[str, DayStat] = {}
    for s in stats:
        t = totals.setdefault(s.backend, DayStat("total", s.backend))
        t.runs += s.runs
        t.ok += s.ok
        t.moved_on += s.moved_on
        t.seconds += s.seconds
        t.est_tokens += s.est_tokens
    rows.append("-" * 46)
    for t in totals.values():
        rows.append(f"{'total':6} {t.backend:7} {t.runs:4} {t.ok_rate * 100:4.0f} "
                    f"{t.avg_seconds:6.1f} {t.escalation_rate * 100:5.0f} {t.est_tokens:7}")
    rows.append("esc% = runs where Mega Zword had to move on to another AI.")
    return "\n".join(rows)
