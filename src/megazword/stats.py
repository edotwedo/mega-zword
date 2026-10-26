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
        requests = max(1, int(runlog._number(r.get("requests", 1))))
        s.runs += requests
        s.ok += requests * bool(r.get("ok"))
        s.moved_on += requests * (not r.get("ok"))
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


PAID_OR_SUB = frozenset({"claude", "codex", "gemini", "grok", "cmdc", "openrouter"})


def is_free_backend(backend: str) -> bool:
    name = backend.lower()
    if name in PAID_OR_SUB:
        return False
    if name.startswith(("cmdc", "openrouter-laguna")):
        return False
    return True


def free_table(path: Path, days: int = 7, today: date | None = None) -> str:
    """Detailed free vs paid breakdown scorecard."""
    today = today or datetime.now().astimezone().date()
    first = today - timedelta(days=days - 1)
    
    backend_stats: dict[str, dict] = {}
    for r in runlog.read(path):
        day = _local_day(r["time"])
        if day is None or not first <= day <= today:
            continue
        b = str(r.get("backend", "unknown"))
        s = backend_stats.setdefault(b, {"runs": 0, "ok": 0, "seconds": 0.0, "tokens": 0, "escalated": 0})
        requests = max(1, int(runlog._number(r.get("requests", 1))))
        ok = bool(r.get("ok"))
        s["runs"] += requests
        s["ok"] += requests * ok
        s["seconds"] += runlog._number(r.get("seconds"))
        s["tokens"] += int(runlog._number(r.get("est_tokens")))
        used = r.get("backends_used", [b])
        if len(used) > 1 and used[0] == b and r.get("final_backend") != b:
            s["escalated"] += 1

    if not backend_stats:
        return "[megazword] no runs in this period"

    rows = [f"{'Backend':<26} {'Type':<9} {'Runs':>6} {'OK%':>7} {'Tokens':>11} {'Avg Sec':>8} {'Escalated':>10}"]
    rows.append("-" * 80)

    total_free_runs = 0
    total_free_ok = 0
    total_free_tokens = 0
    total_paid_runs = 0
    total_paid_ok = 0
    total_paid_tokens = 0

    for b, s in sorted(backend_stats.items(), key=lambda x: x[1]["runs"], reverse=True):
        is_free = is_free_backend(b)
        b_type = "FREE" if is_free else "SUB/PAID"
        ok_pct = (s["ok"] / s["runs"] * 100) if s["runs"] else 0.0
        avg_s = (s["seconds"] / s["runs"]) if s["runs"] else 0.0
        rows.append(f"{b:<26} {b_type:<9} {s['runs']:>6} {ok_pct:>6.1f}% {s['tokens']:>11,} {avg_s:>7.1f}s {s['escalated']:>10}")
        if is_free:
            total_free_runs += s["runs"]
            total_free_ok += s["ok"]
            total_free_tokens += s["tokens"]
        else:
            total_paid_runs += s["runs"]
            total_paid_ok += s["ok"]
            total_paid_tokens += s["tokens"]

    rows.append("=" * 80)
    total_runs = total_free_runs + total_paid_runs
    total_tokens = total_free_tokens + total_paid_tokens
    free_pct = (total_free_runs / total_runs * 100) if total_runs else 0.0
    paid_pct = (total_paid_runs / total_runs * 100) if total_runs else 0.0
    free_ok = (total_free_ok / total_free_runs * 100) if total_free_runs else 0.0
    paid_ok = (total_paid_ok / total_paid_runs * 100) if total_paid_runs else 0.0
    free_tok_pct = (total_free_tokens / total_tokens * 100) if total_tokens else 0.0
    paid_tok_pct = (total_paid_tokens / total_tokens * 100) if total_tokens else 0.0

    rows.append(f"FREE MODELS TOTAL: {total_free_runs} runs ({free_pct:.1f}%) | Success: {free_ok:.1f}% | Tokens: {total_free_tokens:,} ({free_tok_pct:.1f}%)")
    rows.append(f"SUB/PAID TOTAL:    {total_paid_runs} runs ({paid_pct:.1f}%) | Success: {paid_ok:.1f}% | Tokens: {total_paid_tokens:,} ({paid_tok_pct:.1f}%)")
    return "\n".join(rows)
