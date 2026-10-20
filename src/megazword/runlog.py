"""Read Mega Zword's append-only run log and summarize recent activity."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass
class RunSummary:
    backend: str
    runs: int = 0
    ok: int = 0
    rejected: int = 0
    failed: int = 0
    seconds: float = 0.0
    prompt_chars: int = 0
    answer_chars: int = 0
    est_tokens: int = 0


def read(path: Path) -> list[dict]:
    """Read valid JSON records, skipping malformed or incomplete lines."""
    if not path.exists():
        return []
    records = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            record = json.loads(line)
            if isinstance(record, dict) and record.get("backend") and record.get("time"):
                records.append(record)
        except (ValueError, TypeError):
            continue
    return records


def _time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (ValueError, TypeError, AttributeError):
        return None


def summarize(path: Path, window: timedelta, now: datetime | None = None,
              project: str | None = None) -> dict[str, RunSummary]:
    """Summarize records in the trailing time window, grouped by backend."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    cutoff = now - window
    summaries: dict[str, RunSummary] = {}
    for record in read(path):
        if project is not None and record.get("project") != project:
            continue
        stamp = _time(record["time"])
        if stamp is None or stamp < cutoff or stamp > now:
            continue
        backend = str(record["backend"])
        requests = max(1, int(_number(record.get("requests", 1))))
        # A coding run that failed over is split by the requests each backend
        # served, so fair share and the grant ledger see who actually did the work.
        by = record.get("requests_by_backend")
        shares = ({str(k): int(_number(v)) for k, v in by.items() if int(_number(v)) > 0}
                  if isinstance(by, dict) else {})
        if len(shares) < 2:
            shares = {backend: requests}
        total = sum(shares.values())
        for name, count in shares.items():
            part = count / total
            item = summaries.setdefault(name, RunSummary(name))
            item.runs += count
            # The outcome belongs to the run's final backend; the others failed over.
            ok = bool(record.get("ok")) and (len(shares) == 1 or name == record.get("final_backend"))
            item.ok += count * ok
            item.rejected += count * bool(record.get("rejected"))
            item.failed += count * (not ok and not record.get("rejected"))
            item.seconds += _number(record.get("seconds")) * part
            item.prompt_chars += int(_number(record.get("prompt_chars")) * part)
            item.answer_chars += int(_number(record.get("answer_chars")) * part)
            item.est_tokens += int(_number(record.get("est_tokens")) * part)
    return summaries


def _number(value) -> float:
    """A finite number or 0. JSON's NaN/Infinity would crash int() in the totals."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0
