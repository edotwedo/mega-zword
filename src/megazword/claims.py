"""Pure claim tracking from chronological room messages (never lane names)."""

import os
import re
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone


# "Beacon-17: ..." or "Beacon-17 (claude-pc): ..."
PREFIX = re.compile(r"^([A-Za-z]+-\d+)(?:\s*\([^)]*\))?:\s*(.*)$", re.DOTALL)
STALE = timedelta(hours=24)  # TEAM.md default; night shifts can shorten it
# A night shift needs a shorter leash than a normal day. Set the env var to override.
STALE_ENV = "MEGAZWORD_CLAIM_STALE_MINUTES"
CLAIM = re.compile(
    r"^(?:claim(?:ing)?|tak(?:e|ing)|reserv(?:e|ing)|grab(?:bing)?|owning)\b[\s:,-]*(.*)$",
    re.IGNORECASE,
)
RELEASE = re.compile(
    r"\b(releasing|released|dropping|dropped|landed|merged|shipped|pushed|fixed|"
    r"done|complete|completed|reassigned|took over)\b",
    re.IGNORECASE,
)
ITEM = re.compile(r"#(\d+)\b|\bitem\s+(\d+)\b", re.IGNORECASE)


def claim_from_text(text):
    """A claim is the FIRST LINE of a post and starts with an ownership verb.

    Two things this fixes (both seen on the night of 2026-10-19):
    - "Beacon-17: taking #5" went unregistered, because only the literal word
      "claiming" counted, so the WIP cap let the same item be claimed twice.
    - The previous full-match let one long post swallow every following line as
      its "item", so item numbers from the rest of the post leaked into
      conflict checks.
    """
    prefix = PREFIX.match(text)
    if not prefix:
        return None
    body = prefix[2].strip()
    if not body:
        return None
    match = CLAIM.match(body.splitlines()[0])
    if not match:
        return None
    # Stop at the first sentence: "claiming #4. Also landed #18" claims only #4.
    item = re.split(r"\.\s", match[1], maxsplit=1)[0].strip()
    # A claim must point at an item. "taking conductor for the rest of the night"
    # is not a claim on anything, and registering it blocks the room on a phrase.
    if not item or not item_numbers(item):
        return None
    return (prefix[1], item)


def item_numbers(text):
    return {int(a or b) for a, b in ITEM.findall(text)}


def _field(message, name, default=""):
    return message.get(name, default) if isinstance(message, Mapping) else getattr(message, name, default)


def stale_window() -> timedelta:
    try:
        minutes = int(os.environ.get(STALE_ENV, "1440"))
    except ValueError:
        minutes = 1440
    return timedelta(minutes=max(1, minutes))


def _fresh(stamp, now, window=None):
    if now is None:
        return True
    try:
        when = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return True
    when = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
    return now - when <= (window or STALE)


def active_claims(messages, now=None, stale=None):
    """Return designation -> (item text, message ID, time), one open claim per seat.

    The newest claim wins: a seat that claims again (after a release or with --force)
    is working on the new item, so the old one must not keep blocking the room.
    With ``now``, claims older than the stale window are dropped.
    """
    window = stale or stale_window()
    return {d: c for d, c in _open_claims(messages).items() if _fresh(c[2], now, window)}


NEGATED = re.compile(
    r"\b(?:not|never|no|isn't|isnt|hasn't|hasnt|won't|wont)\s+(?:yet\s+)?\w+", re.IGNORECASE
)


def _released(body: str) -> bool:
    """True when the post says something landed or was released.

    Negated phrases are removed first, so "#10 is not done yet" is not read as a
    release (and, just as importantly, removing the word "not" alone would turn
    it into one).
    """
    return bool(RELEASE.search(NEGATED.sub(" ", body)))


def announces_release(body: str, numbers: set[int]) -> bool:
    """True when a post says this item landed or was released, whoever posted it.

    Work gets reassigned and shipped by other people, so the holder's silence is
    not evidence the item is still theirs. The item number is required, so a
    passing "done" cannot free someone else's unrelated claim.
    """
    if not numbers or not (numbers & item_numbers(body)):
        return False
    return _released(body)


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
            # Newest claim wins: one open claim per seat, so a stale first claim
            # cannot block the next item forever.
            active[designation] = (claim[1], _field(message, "id", _field(message, "remote_id", 0)),
                                   _field(message, "time"))
            continue
        body = prefix[2]
        # Any seat's release closes the item it names, not only the holder's own
        # post. On 2026-10-19 a seat went dark holding #4, the conductor
        # reassigned and shipped it, and `room claims` - the ledger the WIP cap
        # trusts - still showed the dead seat holding it.
        for holder, (held, _id, _time) in list(active.items()):
            if announces_release(body, item_numbers(held)):
                del active[holder]
        if designation in active:
            item = active[designation][0]
            numbers = item_numbers(item)
            matches = bool(numbers & item_numbers(body)) if numbers else item.casefold() in body.casefold()
            if re.search(r"\b(releasing|released|dropping|dropped)\b", body, re.I) or (
                matches and _released(body)
            ):
                del active[designation]
    return active


def claim_conflicts(claims):
    """Return (first designation, second designation, item number) conflicts."""
    entries = list(claims.items())
    return [(a, b, number) for i, (a, first) in enumerate(entries)
            for b, second in entries[i + 1:]
            for number in sorted(item_numbers(first[0]) & item_numbers(second[0]))]
