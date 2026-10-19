"""Pure claim tracking from chronological room messages (never lane names)."""

import re
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone


# "Beacon-17: ..." or "Beacon-17 (claude-pc): ..."
PREFIX = re.compile(r"^([A-Za-z]+-\d+)(?:\s*\([^)]*\))?:\s*(.*)$", re.DOTALL)
STALE = timedelta(hours=24)  # TEAM.md: a claim with no release frees up after 24 hours
CLAIM = re.compile(r"claiming\s+(.+)", re.IGNORECASE | re.DOTALL)
ITEM = re.compile(r"#(\d+)\b|\bitem\s+(\d+)\b", re.IGNORECASE)


def claim_from_text(text):
    prefix = PREFIX.match(text)
    claim = CLAIM.fullmatch(prefix[2]) if prefix else None
    return (prefix[1], claim[1].strip()) if claim and claim[1].strip() else None


def item_numbers(text):
    return {int(a or b) for a, b in ITEM.findall(text)}


def _field(message, name, default=""):
    return message.get(name, default) if isinstance(message, Mapping) else getattr(message, name, default)


def _fresh(stamp, now):
    if now is None:
        return True
    try:
        when = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return True
    when = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
    return now - when <= STALE


def active_claims(messages, now=None):
    """Return designation -> (item text, message ID, time), retaining the first open claim.

    With ``now``, claims older than STALE are dropped (the claimer is presumed gone).
    """
    return {d: c for d, c in _open_claims(messages).items() if _fresh(c[2], now)}


def _open_claims(messages):
    active = {}
    names = {}
    for message in messages:
        text = _field(message, "text")
        prefix = PREFIX.match(text)
        if not prefix:
            continue
        key = prefix[1].lower()
        designation = names.setdefault(key, prefix[1])
        claim = claim_from_text(text)
        if claim:
            active.setdefault(designation, (claim[1], _field(message, "id", _field(message, "remote_id", 0)),
                                             _field(message, "time")))
        elif designation in active:
            body = prefix[2]
            item = active[designation][0]
            numbers = item_numbers(item)
            matches = bool(numbers & item_numbers(body)) if numbers else item.casefold() in body.casefold()
            if re.search(r"\b(releasing|released)\b", body, re.I) or (
                re.search(r"\b(landed|done)\b", body, re.I) and matches
            ):
                del active[designation]
    return active


def claim_conflicts(claims):
    """Return (first designation, second designation, item number) conflicts."""
    entries = list(claims.items())
    return [(a, b, number) for i, (a, first) in enumerate(entries)
            for b, second in entries[i + 1:]
            for number in sorted(item_numbers(first[0]) & item_numbers(second[0]))]
