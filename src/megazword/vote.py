"""Ballots in the room, counted by the room.

Phil, 2026-10-21: the team should be able to vote on a change instead of one seat deciding and
calling it agreed. This is mechanism 7 of `docs/SYSTEM-DRAFT.md`: a proposal has an id, every seat
casts once, and the tally is read from the room rather than trusted from a summary.

    megazword vote new "Replace the rule set" --items M1,M2,M3
    megazword vote cast P1 M1=yes M2=no M3=abstain | one-line reason
    megazword vote cast P1 yes | whole-proposal vote
    megazword vote tally P1

One vote per seat: a later cast by the same seat replaces the earlier one, because changing your
mind is not cheating. A seat that never votes is reported as missing, never assumed.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Callable

from . import config
from .filelock import write_atomic
from .resume import DESIGNATION

PROPOSAL = re.compile(rf"^\s*({DESIGNATION})\s*:\s*vote\s+(P\d+)\b(.*)$", re.DOTALL | re.IGNORECASE)
ITEM = re.compile(r"\b([A-Z]{1,3}\d+)\s*=\s*(yes|no|abstain)\b", re.IGNORECASE)
WHOLE = re.compile(r"^\s*(yes|no|abstain)\b", re.IGNORECASE)
CHOICES = ("yes", "no", "abstain")


def _field(message, name, default=""):
    return message.get(name, default) if isinstance(message, dict) else getattr(message, name, default)


def votes_dir(home: Path | None = None) -> Path:
    return (home or config.HOME) / "votes"


def proposal_path(identifier: str, home: Path | None = None) -> Path:
    return votes_dir(home) / f"{identifier.upper()}.json"


def next_id(home: Path | None = None) -> str:
    """P1, P2, ... in creation order; never reuses a retired number."""
    highest = 0
    try:
        for path in votes_dir(home).glob("P*.json"):
            digits = re.sub(r"\D", "", path.stem)
            highest = max(highest, int(digits or 0))
    except OSError:
        pass
    return f"P{highest + 1}"


def create(question: str, items: list[str] | None = None, *, home: Path | None = None,
           say: Callable | None = None, room_name: str = "hive") -> dict:
    """Open a ballot and announce it in the room."""
    question = " ".join((question or "").split())
    if not question:
        raise ValueError("a ballot needs a question")
    items = [item.strip().upper() for item in (items or []) if item.strip()]
    if any(not re.fullmatch(r"[A-Z]{1,3}\d+", item) for item in items):
        raise ValueError("items look like M1, M2, ...")
    identifier = next_id(home)
    record = {"id": identifier, "question": question, "items": items}
    path = proposal_path(identifier, home)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, json.dumps(record) + "\n")
    line = f"BALLOT {identifier} is open: {question}"
    if items:
        line += " | vote each: " + " ".join(f"{item}=yes|no|abstain" for item in items)
        line += f" | cast: <designation>: vote {identifier} " + " ".join(f"{i}=yes" for i in items)
    else:
        line += f" | cast: <designation>: vote {identifier} yes|no|abstain"
    if say is None:
        from . import room
        room.say(room_name, line, author="floor", home=home, write=lambda _s: None)
    else:
        say(room_name, line, author="floor")
    record["announced"] = line
    return record


def parse_vote(text: str):
    """(designation, proposal, choices, reason) from one room line, or None.

    A cast may vote the whole proposal or named items, never both by accident: if any item pairs
    are present they are the vote, and a stray leading yes/no is ignored.
    """
    match = PROPOSAL.match(text or "")
    if not match:
        return None
    designation, identifier, rest = match[1], match[2].upper(), match[3]
    reason = rest.split("|", 1)[1].strip() if "|" in rest else ""
    body = rest.split("|", 1)[0]
    pairs = {item.upper(): choice.lower() for item, choice in ITEM.findall(body)}
    if pairs:
        return designation, identifier, pairs, reason
    whole = WHOLE.match(body.strip())
    if whole:
        return designation, identifier, {"": whole[1].lower()}, reason
    return None


def collect(messages, identifier: str) -> dict:
    """seat -> vote. A later cast by the same seat replaces the earlier one.

    Counted by the designation written in the room, deliberately: this is an internal tally for one
    team on one box, not an election. A forged vote is visible in the log for a human to spot, and
    hardening it once already threw away real votes from seats that share the claude-pc lane.
    """
    seen: dict[str, dict] = {}
    for message in messages:
        parsed = parse_vote(_field(message, "text"))
        if not parsed or parsed[1] != identifier.upper():
            continue
        designation, _identifier, choices, reason = parsed
        seen[designation.casefold()] = {"seat": designation, "choices": choices, "reason": reason,
                                        "time": _field(message, "time")}
    return seen


def record(identifier: str, home: Path | None = None) -> dict | None:
    try:
        return json.loads(proposal_path(identifier, home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def tally(messages, identifier: str, *, seats: list[str] | None = None) -> dict:
    """Count the ballot. Quorum is two thirds of the asked seats, minimum three, never padded."""
    proposal = record(identifier) or {"id": identifier.upper(), "items": []}
    identifier = proposal["id"]
    cast = collect(messages, identifier)
    asked = [seat for seat in (seats or []) if seat]
    item_names = proposal.get("items") or []
    result = {"id": identifier, "question": proposal.get("question", ""), "items": item_names,
              "cast": cast, "counts": {}, "quorum": 0, "reached": False,
              "missing": [seat for seat in asked if seat.casefold() not in cast], "incomplete": []}
    for item in item_names:
        counts = {choice: 0 for choice in CHOICES}
        for vote in cast.values():
            choice = vote["choices"].get(item)
            if choice:
                counts[choice] += 1
        result["counts"][item] = counts
    # Two thirds of the seats asked, with a floor of two so a single vote cannot decide alone.
    result["quorum"] = max(2, -(-len(asked) * 2 // 3)) if asked else 3
    result["reached"] = len(cast) >= result["quorum"]
    if item_names:
        result["incomplete"] = [vote["seat"] for vote in cast.values()
                                if any(item not in vote["choices"] for item in item_names)]
    return result


def render(result: dict) -> str:
    lines = [f"{result['id']}: {result['question']}"]
    if result["items"]:
        for item in result["items"]:
            counts = result["counts"][item]
            lines.append(f"  {item}: yes {counts['yes']}  no {counts['no']}  abstain {counts['abstain']}")
    for seat, vote in sorted(result["cast"].items(), key=lambda pair: pair[0]):
        detail = " ".join(f"{item}={choice}" for item, choice in sorted(vote["choices"].items()))
        reason = f"  | {vote['reason']}" if vote["reason"] else ""
        lines.append(f"  {vote['seat']}: {detail or '(no choice parsed)'}{reason}")
    if result["missing"]:
        lines.append(f"  not voted: {', '.join(result['missing'])}")
    if result["incomplete"]:
        lines.append(f"  voted but skipped an item: {', '.join(result['incomplete'])}")
    state = "QUORUM REACHED" if result["reached"] else f"no quorum (needs {result['quorum']})"
    lines.append(f"  {len(result['cast'])} votes - {state}")
    return "\n".join(lines)


def cast(identifier: str, verdicts: dict, reason: str = "", *,
         home: Path | None = None, seat: str | None = None, say: Callable | None = None,
         room_name: str = "hive") -> str:
    """Post one seat's vote. The room is the ballot box."""
    import os
    seat = (seat or os.environ.get("MEGAZWORD_SEAT") or "").strip()
    if not seat:
        raise ValueError("set MEGAZWORD_SEAT so the vote carries your designation")
    if not verdicts:
        raise ValueError("vote yes, no, abstain, or M1=yes M2=no")
    malformed = {key: value for key, value in verdicts.items()
                 if value.lower() not in CHOICES or (key and not re.fullmatch(r"[A-Z]{1,3}\d+", key.upper()))}
    if malformed:
        raise ValueError(f"each choice must be yes, no or abstain: {sorted(malformed)}")
    body = " ".join(f"{key.upper()}={value.lower()}" if key else value.lower()
                    for key, value in verdicts.items())
    line = f"{seat}: vote {identifier.upper()} {body}"
    if reason:
        line += f" | {' '.join(reason.split())}"
    if say is None:
        from . import room
        room.say(room_name, line, author=seat, home=home, write=lambda _s: None)
    else:
        say(room_name, line, author=seat)
    return line


def parse_verdicts(words: list[str]) -> dict:
    """['M1=yes','M2=no'] or ['yes'] -> the dict `cast` wants."""
    verdicts: dict[str, str] = {}
    for word in words:
        if "=" in word:
            key, value = word.split("=", 1)
            verdicts[key.strip().upper()] = value.strip().lower()
        else:
            verdicts[""] = word.strip().lower()
    return verdicts


def command(args) -> int:
    """CLI. `new` announces, `cast` posts, `tally` reads the room fresh and counts."""
    from . import room
    action = getattr(args, "action", "tally")
    if action == "new":
        items = [item.strip().upper() for item in (getattr(args, "items", "") or "").split(",") if item.strip()]
        question = (getattr(args, "question", "") or getattr(args, "proposal", "") or "").strip()
        try:
            proposal = create(question, items)
        except ValueError as exc:
            print(f"[megazword vote] {exc}")
            return 2
        print(proposal["announced"])
        return 0
    if action == "cast":
        line = cast(args.proposal, parse_verdicts(args.choices), getattr(args, "reason", "") or "",
                    seat=getattr(args, "seat", None))
        print(line)
        return 0
    cfg = config.load()
    messages = room.claim_messages("hive", cfg)          # fresh from the Worker, never the cache
    seats = [line.strip("| ").split()[0] for line in
             (record(args.proposal) or {}).get("asked", [])]
    print(render(tally(messages, args.proposal, seats=seats)))
    return 0


def add_parser(sub) -> None:
    parser = sub.add_parser("vote", help="ballot in the room: new, cast, tally; one vote per seat")
    parser.add_argument("action", nargs="?", default="tally", choices=("new", "cast", "tally"))
    parser.add_argument("proposal", nargs="?", default="", help="proposal id, e.g. P1")
    parser.add_argument("choices", nargs="*", default=[], help="yes|no|abstain, or M1=yes M2=no")
    parser.add_argument("--items", default="", help="for new: M1,M2,...")
    parser.add_argument("--question", default="", help="for new: what is being voted on")
    parser.add_argument("--reason", default="", help="one line, why you voted that way")
    parser.add_argument("--seat", default="", help="override MEGAZWORD_SEAT")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", nargs="?", default="tally", choices=("new", "cast", "tally"))
    parser.add_argument("proposal", nargs="?", default="")
    parser.add_argument("choices", nargs="*", default=[])
    parser.add_argument("--items", default="")
    parser.add_argument("--question", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--seat", default="")
    return command(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
