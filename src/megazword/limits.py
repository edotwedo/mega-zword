"""Spot "you've hit your usage limit" errors and work out when usage is back.

When an AI fails with one, Mega Zword marks it out (config [out]) until the
reset time, so auto-pick stops wasting a call on it every run.

Wordings seen or documented:
- Codex: "You've hit your usage limit. Upgrade to Pro (...) or try again at
  2:39 AM." (captured live 2026-10-11; may also carry a date for weekly resets)
- Claude Code: "Claude AI usage limit reached|1760000000" (epoch seconds) and
  "5-hour limit reached ∙ resets 3am" / "Your limit will reset at 3am".
- Anything else that says usage limit / quota / rate limit with a time.
If no reset time can be read, the AI is marked out for FALLBACK.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

FALLBACK = timedelta(hours=1)

LIMIT_WORDS = re.compile(
    r"usage limit|limit reached|hit your (?:usage )?limit|quota (?:exceeded|exhausted)"
    r"|rate limit exceeded|out of (?:credits|usage)|too many requests|\b429\b", re.I)

_EPOCH = re.compile(r"limit reached\|(\d{10})\b", re.I)
_MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
_WHEN = re.compile(
    r"(?:try again|reset[s]?|available again|resets? at|again at)\D{0,12}?"
    r"(?:(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+"
    r"(?P<day>\d{1,2})(?:st|nd|rd|th)?,?\s*(?P<year>\d{4})?,?\s*(?:at\s+)?)?"
    r"(?P<hour>\d{1,2})(?::(?P<min>\d{2}))?\s*(?P<ampm>[ap]\.?m\.?)", re.I)
_IN = re.compile(r"(?:try again|resets?|again)\s+in\s+((?:\d+\s*(?:days?|d|hours?|hrs?|h|"
                 r"minutes?|mins?|m)\s*,?\s*(?:and\s*)?)+)", re.I)
_PART = re.compile(r"(\d+)\s*(days?|d|hours?|hrs?|h|minutes?|mins?|m)\b", re.I)


@dataclass
class LimitHit:
    until: datetime
    exact: bool  # False when we fell back to FALLBACK


def detect(text: str, now: datetime | None = None) -> LimitHit | None:
    """A LimitHit if `text` is a usage-limit error, else None."""
    text = (text or "").replace("’", "'")
    if not LIMIT_WORDS.search(text):
        return None
    now = now or datetime.now().astimezone()
    until = _reset_time(text, now)
    return LimitHit(until, True) if until else LimitHit(now + FALLBACK, False)


def _reset_time(text: str, now: datetime) -> datetime | None:
    if m := _EPOCH.search(text):
        return datetime.fromtimestamp(int(m.group(1))).astimezone()
    if m := _IN.search(text):
        total = timedelta()
        for n, unit in _PART.findall(m.group(1)):
            u = unit.lower()[0]
            total += timedelta(days=int(n)) if u == "d" else \
                timedelta(hours=int(n)) if u == "h" else timedelta(minutes=int(n))
        if total:
            return now + total
    if m := _WHEN.search(text):
        hour = int(m.group("hour")) % 12 + (12 if m.group("ampm").lower().startswith("p") else 0)
        minute = int(m.group("min") or 0)
        if m.group("mon"):
            month = _MONTHS.index(m.group("mon").lower()[:3]) + 1
            year = int(m.group("year") or now.year)
            when = now.replace(year=year, month=month, day=int(m.group("day")),
                               hour=hour, minute=minute, second=0, microsecond=0)
            if not m.group("year") and when < now - timedelta(days=1):
                when = when.replace(year=year + 1)
            return when
        when = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return when if when > now else when + timedelta(days=1)  # next occurrence
    return None
