"""Credit ledger: one-time grants, what's left, how long it lasts, and a hard
block on any source that could bill Phil.

Balances are estimates. Mega Zword only sees its own run log (characters / 4),
so `megazword credits set NAME --used N` records the real figure from the
provider's console and later runs are counted on top of it.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .routing import TENCENT_BACKENDS

# Tencent TokenHub: one-time 1M-token grant per model, valid one year, postpaid
# off by default (docs/FREE-MODEL-ROSTER.md). Phil unlocked six of 34 for $1 each.
DEFAULTS = {name: {"kind": "grant", "grant_tokens": 1_000_000, "used_reported": 0,
                   "reported_at": None, "expires": None, "can_bill": False}
            for name in TENCENT_BACKENDS}

BURN_DAYS = 3
WARN_DAYS = (7, 2)


def path(home: Path | None = None) -> Path:
    if home is None:
        from .config import HOME
        home = HOME
    return home / "credits.json"


def load(home: Path | None = None) -> dict[str, dict]:
    entries = {name: dict(entry) for name, entry in DEFAULTS.items()}
    try:
        saved = json.loads(path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    for name, entry in saved.items() if isinstance(saved, dict) else ():
        if isinstance(entry, dict):
            entries[name] = {**entries.get(name, {}), **entry}
    return entries


def save(entries: dict[str, dict], home: Path | None = None) -> None:
    target = path(home)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(target)


ALIASES = {"tencent": "tencent-deepseek-v4-pro"}  # same grant, older backend name


def mark_used_up(name: str, why: str, home: Path | None = None) -> bool:
    """A provider refused for lack of free quota (HTTP 402): stop routing to it.

    Records the whole grant as used, with the reason, so `megazword credits` shows
    it and routing skips it. `credits set NAME --used N` with the console figure
    puts it back. Returns False for sources the ledger doesn't track.
    """
    name = ALIASES.get(name, name)
    entries = load(home)
    if name not in entries:
        return False
    entry = entries[name]
    entry["used_reported"] = entry.get("grant_tokens") or 1
    entry["reported_at"] = datetime.now(timezone.utc).isoformat()
    entry["note"] = f"{why} ({datetime.now():%Y-%m-%d %H:%M})"
    save(entries, home)
    return True


def _logged_tokens(name: str, since: datetime | None, log_path: Path,
                   now: datetime) -> int:
    from .runlog import summarize
    window = now - since if since else timedelta(days=3650)
    item = summarize(log_path, window, now=now).get(name)
    return item.est_tokens if item else 0


def status(name: str, entry: dict, log_path: Path,
           now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    since = None
    if entry.get("reported_at"):
        since = datetime.fromisoformat(entry["reported_at"])
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
    used = int(entry.get("used_reported") or 0) + _logged_tokens(name, since, log_path, now)
    grant = entry.get("grant_tokens")
    left = None if grant is None else max(0, int(grant) - used)
    burn = _logged_tokens(name, now - timedelta(days=BURN_DAYS), log_path, now) / BURN_DAYS
    days = None if left is None or burn <= 0 else left / burn
    expires = entry.get("expires")
    if expires and days is not None:
        days = min(days, max(0.0, (date.fromisoformat(expires) - now.date()).days))
    return {"name": name, "kind": entry.get("kind", "grant"), "used": used,
            "left": left, "grant": grant, "burn_per_day": burn, "days_left": days,
            "can_bill": bool(entry.get("can_bill")), "blocked": blocked_reason(entry, left, now)}


def blocked_reason(entry: dict, left: int | None, now: datetime | None = None) -> str:
    """Why routing must skip this source, or "" if it may be used."""
    now = now or datetime.now(timezone.utc)
    if entry.get("can_bill"):
        return "can bill after the free amount; turn billing off, then `credits set --can-bill no`"
    if left is not None and left <= 0:
        return "grant used up"
    if entry.get("expires") and date.fromisoformat(entry["expires"]) < now.date():
        return "grant expired"
    return ""


def blocked(names: list[str], home: Path | None = None,
            log_path: Path | None = None) -> dict[str, str]:
    """Blocked sources among names, with reasons. Unlisted sources pass."""
    entries = load(home)
    listed = [n for n in names if n in entries]
    if not listed:
        return {}
    if log_path is None:
        from .config import HOME
        log_path = HOME / "log.jsonl"
    found = {}
    for name in listed:
        reason = status(name, entries[name], log_path)["blocked"]
        if reason:
            found[name] = reason
    return found


def _fmt(n) -> str:
    if n is None:
        return "?"
    return f"{n / 1_000_000:.2f}M" if n >= 100_000 else f"{n / 1000:.0f}k"


def table(home: Path | None = None, log_path: Path | None = None) -> str:
    entries = load(home)
    if log_path is None:
        from .config import HOME
        log_path = HOME / "log.jsonl"
    rows = [status(name, entry, log_path) for name, entry in sorted(entries.items())]
    lines = ["Source                                 left / grant    burn/day  runway   note"]
    for r in rows:
        runway = "-" if r["days_left"] is None else f"{r['days_left']:.0f}d"
        note = r["blocked"] or ""
        if note and entries[r["name"]].get("note"):
            note += ": " + entries[r["name"]]["note"]
        if not note and r["days_left"] is not None and r["days_left"] <= WARN_DAYS[0]:
            note = "LOW: under a week left at current pace"
        lines.append(f"{r['name']:38} {_fmt(r['left']):>6} / {_fmt(r['grant']):<7} "
                     f"{_fmt(r['burn_per_day']):>7}  {runway:>6}   {note}")
    total = sum(r["left"] or 0 for r in rows if not r["blocked"])
    lines.append(f"\nUsable grant tokens left: {_fmt(total)} (estimate). "
                 "Record real figures from each console with `megazword credits set`.")
    from . import budget
    lines.append(budget.line())
    return "\n".join(lines)


def command(args, home: Path | None = None, log_path: Path | None = None) -> int:
    if args.action == "set":
        entries = load(home)
        entry = entries.setdefault(args.name, {"kind": "grant", "grant_tokens": None,
                                               "used_reported": 0, "reported_at": None,
                                               "expires": None, "can_bill": False})
        if args.used is not None:
            entry["used_reported"] = args.used
            entry["reported_at"] = datetime.now(timezone.utc).isoformat()
        if args.grant is not None:
            entry["grant_tokens"] = args.grant
        if args.expires is not None:
            date.fromisoformat(args.expires)
            entry["expires"] = args.expires
        if args.can_bill is not None:
            entry["can_bill"] = args.can_bill == "yes"
        save(entries, home)
    print(table(home, log_path))
    return 0
