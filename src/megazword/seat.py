"""Seat lifecycle: who is seated, and how a spent seat hands off.

Phil, 2026-10-21: "if a user's context window get full, they are to retire and alert me
to the need for a replacement. If you are able to do this on your own, even better."

    megazword seat status          the roster, joined with saved session cards and worktrees
    megazword seat watch           report open claims whose holders have gone silent
    megazword seat retire X        write the handoff, post one line, page Phil
    megazword seat replace X       the relaunch line and the first prompt for the replacement

`status` reads local files only: no AI calls, no network. `retire` posts one room line and
one ntfy page, and reports a dead room instead of failing, because losing a handoff to a
dropped connection is worse than a noisy line in the output.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .briefing import publish, snapshot
from . import claims
from .filelock import write_atomic
from .guard import scrub
from .resume import ROSTER, read_recorded, seats

HANDOFFS = Path(__file__).resolve().parents[2] / "docs" / "handoffs"
SEATS_ROOT = Path.home() / "mz-seats"


def roster() -> list[tuple[str, str]]:
    """(designation, cli) in roster order. A roster that cannot be read is not fatal."""
    try:
        return seats(ROSTER.read_text(encoding="utf-8"))
    except OSError:
        return []


def directory(designation: str) -> Path:
    """Where this seat was launched, from the respawn record, else its conventional home."""
    recorded = read_recorded()
    row = recorded.get(designation.lower()) or {}
    return Path(row["dir"]) if row.get("dir") else SEATS_ROOT / designation.lower()


def cards(home: Path | None = None) -> dict:
    return {c["seat"]: c for c in snapshot(home)["cards"]}


def room_summary(home: Path | None = None) -> dict:
    """Per seat: its last room line and its kind counts, from the LOCAL cache only.

    No seat on the team publishes a briefing card yet, so a status built from cards alone
    says "no card" for everyone, including seats that have been posting all night. The room
    already knows what each seat is doing. This stays local on purpose: `status` must remain
    safe to run from a seat that is nearly out of room, and a network read can hang.
    """
    from . import room as room_module
    try:
        messages = room_module.read_messages("hive", home)
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    return {row["designation"].casefold(): row for row in claims.summarize_kinds(messages)}


def status_rows(home: Path | None = None) -> list[dict]:
    saved = cards(home)
    spoken = room_summary(home)
    rows = []
    for designation, cli in roster():
        card = saved.get(designation.casefold(), {})
        said = spoken.get(designation.casefold(), {})
        where = directory(designation)
        rows.append({
            "designation": designation,
            "cli": cli,
            "dir": str(where),
            "worktree": where.is_dir(),
            # A card is the seat's own report; the room is what it actually said out loud.
            "state": card.get("state", "") or said.get("last_kind", ""),
            "age_minutes": (card.get("age_seconds", 0) // 60) if card else None,
            "next": card.get("next", ""),
            "last": said.get("last", ""),
            "from_room": not card and bool(said),
        })
    return rows


def render_status(rows: list[dict]) -> str:
    if not rows:
        return "seat: no roster rows found in docs/HIVE-ROSTER.md"
    lines = ["Seats on the roster (a card is the seat's own report; otherwise what it last said in the room)"]
    for row in rows:
        if row["age_minutes"] is None:
            age = "room" if row.get("from_room") else "never"
        else:
            age = f"{row['age_minutes']}m ago"
        lines.append(f"  {row['designation']:12} {row['cli']:7} "
                     f"{'worktree' if row['worktree'] else 'NO WORKTREE':12} "
                     f"{(row['state'] or 'silent'):8} {age:>8}")
        if row["next"]:
            lines.append(f"      next: {row['next'][:100]}")
        elif row.get("last"):
            lines.append(f"      said: {row['last'][:100]}")
    lines.append("  usage and floor state: run `megazword usage`")
    return "\n".join(lines)


def watch(room_name: str = "hive", *, home: Path | None = None,
          now: datetime | None = None, read: Callable | None = None) -> list[dict]:
    """One read-only pass: open claims silent longer than the configured leash.

    Read and clock are injectable so callers can inspect a snapshot offline. Do not
    pass ``now`` to active_claims: its age filter hides precisely the old claims we
    need to check. A holder's later room update resets silence, not claim age.
    """
    if read is None:
        from .floor import room_messages
        read = room_messages
    messages = list(read(room_name, home))
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    leash = claims.stale_window()
    last_seen = {}
    for message in messages:
        def field(name):
            return message.get(name, "") if isinstance(message, Mapping) else getattr(message, name, "")

        prefix = claims.PREFIX.match(str(field("text")))
        if not prefix:
            continue
        try:
            stamp = datetime.fromisoformat(str(field("time")).replace("Z", "+00:00"))
        except ValueError:
            continue  # Missing timestamps cannot establish silence.
        stamp = stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)
        key = prefix[1].casefold()
        if key not in last_seen or stamp > last_seen[key]:
            last_seen[key] = stamp

    overdue = []
    for designation, (item, claim_id, _stamp) in sorted(claims.active_claims(messages).items()):
        stamp = last_seen.get(designation.casefold())
        if stamp is not None and now - stamp > leash:
            overdue.append({"designation": designation, "item": item, "claim_id": claim_id,
                            "last_seen": stamp.isoformat(),
                            "silent_minutes": int((now - stamp).total_seconds() // 60),
                            "leash_minutes": int(leash.total_seconds() // 60)})
    return overdue


def _by_designation() -> dict:
    """The roster keyed casefold, because a seat types its own name however it likes.

    Harbor022's review (2026-10-21): `seat retire harbor022` matched nothing, so the handoff
    said "unknown CLI" and `replace` printed no CLI at all. The roster row says Harbor022.
    """
    return {designation.casefold(): cli for designation, cli in roster()}


def cli_for(designation: str) -> str:
    return _by_designation().get(designation.casefold(), "")


def handoff_path(designation: str, now: datetime) -> Path:
    return HANDOFFS / f"{now:%Y-%m-%d}-retired-{designation.lower()}.md"


def newest_handoff(designation: str) -> Path | None:
    found = sorted(HANDOFFS.glob(f"*-retired-{designation.lower()}.md"))
    return found[-1] if found else None


def handoff_text(designation: str, cli: str, reason: str, next_step: str, now: datetime) -> str:
    return (
        f"# {designation} retired {now:%Y-%m-%d %H:%M}Z\n\n"
        f"- Seat: {designation} ({cli or 'unknown CLI'})\n"
        f"- Reason: {reason or 'context window full'}\n"
        f"- Nothing here is finished by being written down; the replacement does the work.\n\n"
        f"## Next step\n\n{next_step or 'Not stated. Ask the conductor.'}\n\n"
        f"## How the replacement starts\n\n"
        f"1. `megazword seat replace {designation}` prints the relaunch command.\n"
        f"2. The replacement reads this file, then `docs/STATUS.md` and "
        f"`docs/HIVE-ROSTER.md`.\n"
        f"3. It reports one line to the Hive room and waits for the conductor's assignment.\n"
    )


def retire(designation: str, *, next_step: str = "", reason: str = "",
           home: Path | None = None, now: datetime | None = None,
           say: Callable | None = None, ping: Callable | None = None,
           cfg=None, room_name: str = "hive") -> dict:
    """Hand the seat off: card, handoff file, one room line, one page to Phil."""
    now = now or datetime.now(timezone.utc)
    cli = cli_for(designation)
    reason = scrub(reason or "")[:200]
    next_step = scrub(next_step or "")[:600]

    card = publish({"seat": designation, "state": "done",
                    "blocked": reason, "next": next_step}, home=home, now=now)

    path = handoff_path(designation, now)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, handoff_text(designation, cli, reason, next_step, now))

    line = f"{designation}: retire - {reason or 'context window full'}"
    if next_step:
        line += f" | next: {next_step[:200]}"
    room_note = ""
    try:
        if say is None:
            from . import room
            room.say(room_name, line, author=designation, home=home,
                     write=lambda _s: None)
        else:
            say(room_name, line, author=designation)
    except (OSError, ValueError, TypeError) as exc:
        room_note = f"room post failed ({type(exc).__name__}) - the handoff file is the record"

    page = f"{designation} retired - a replacement is needed. {next_step[:120]}"
    page_note = ""
    try:
        if ping is None:
            from . import announce
            announce.ping(page, cfg)
        else:
            ping(page)
    except (OSError, ValueError, TypeError) as exc:
        page_note = f"page failed ({type(exc).__name__}) - tell Phil in chat"

    return {"card": card, "handoff": str(path), "line": line,
            "room_note": room_note, "page_note": page_note}


def replace_text(designation: str) -> str:
    rows = {row["designation"].casefold(): row for row in status_rows()}
    row = rows.get(designation.casefold(), {})
    where = row.get("dir") or str(SEATS_ROOT / designation.lower())
    command = (f"scripts/hive_resume.sh --only {designation}"
               if sys.platform.startswith("linux") else
               f"pwsh -File scripts/hive_resume.ps1 -Only {designation}")
    lines = [f"Replace {designation}"
             + (f" ({row['cli']})" if row.get("cli") else ""),
             f"  1. reopen the seat:  {command}",
             f"     worktree: {where}"]
    handoff = newest_handoff(designation)
    if handoff:
        lines.append(f"  2. its first prompt:")
        lines.append(f"     You are {designation}. Read {handoff.relative_to(HANDOFFS.parent.parent)}"
                     f" then docs/STATUS.md and docs/HIVE-ROSTER.md, report one line to the Hive"
                     f" room, and take work only from the conductor.")
    else:
        lines.append("  2. no handoff file found - ask the retiring seat for its next step")
    return "\n".join(lines)


def command(args, cfg=None, write: Callable[[str], None] = print) -> int:
    action = getattr(args, "action", "status") or "status"
    if action == "status":
        write(render_status(status_rows()))
        return 0
    if action == "watch":
        overdue = watch(getattr(args, "room", "hive"))
        for row in overdue:
            write(f"[seat watch] {row['designation']}: silent {row['silent_minutes']}m "
                  f"(claim leash {row['leash_minutes']}m) | {row['item']}")
        if not overdue:
            write("[seat watch] no open claim holders past the silence leash")
        return 0
    designation = getattr(args, "designation", None)
    if not designation:
        write(f"[megazword seat] {action} needs a designation, e.g. `megazword seat {action} Harbor022`")
        return 2
    if action == "replace":
        write(replace_text(designation))
        return 0
    result = retire(designation, next_step=getattr(args, "next", "") or "",
                    reason=getattr(args, "reason", "") or "", cfg=cfg)
    write(f"{designation} retired. handoff: {result['handoff']}")
    write(f"room: {result['room_note'] or 'posted one line'}")
    write(f"phil: {result['page_note'] or 'paged through ntfy'}")
    write(f"replace it with: megazword seat replace {designation}")
    return 0


def add_parser(sub) -> None:
    seat = sub.add_parser(
        "seat",
        help="who is seated, and how a spent seat retires and is replaced",
    )
    seat.add_argument("action", nargs="?", default="status",
                      choices=("status", "watch", "retire", "replace"))
    seat.add_argument("--room", default="hive", help="room to check with watch (default: hive)")
    seat.add_argument("designation", nargs="?", help="the seat to retire or replace")
    seat.add_argument("--next", default="", help="the exact next step for the replacement")
    seat.add_argument("--reason", default="", help="why it stopped (default: context window full)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", nargs="?", default="status",
                        choices=("status", "watch", "retire", "replace"))
    parser.add_argument("--room", default="hive")
    parser.add_argument("designation", nargs="?")
    parser.add_argument("--next", default="")
    parser.add_argument("--reason", default="")
    return command(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
