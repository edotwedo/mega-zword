"""Hive floor: one seat per model we can run. HTTP backends sit without a window."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import sleep, monotonic
from typing import Callable

from . import config
from .backends import Backend

CLI_SEATS = ("claude", "codex", "grok", "gemini")
HTTP_SEATS = ("groq", "cloudflare", "zai", "gemini-api", "nvidia", "mistral", "openrouter")
MINIMUM_CLI = ("claude", "codex", "grok")


@dataclass(frozen=True)
class Seat:
    name: str
    kind: str  # cli | http
    status: str  # seated | empty | out
    until: datetime | None = None
    trains_on_data: bool = False

    def line(self) -> str:
        extra = ""
        if self.status == "out" and self.until is not None:
            extra = f" until {self.until.strftime('%a %b %d %I:%M %p')}"
        elif self.trains_on_data and self.status == "seated":
            extra = " (trains on prompts)"
        return f"{self.kind:4}  {self.name:12} {self.status}{extra}"


def _status(name: str, available: bool, out_until: dict[str, datetime],
            now: datetime) -> tuple[str, datetime | None]:
    until = out_until.get(name)
    if until is not None and until > now:
        return "out", until
    return ("seated" if available else "empty"), None


def roster(backends: dict[str, Backend], out_until: dict[str, datetime] | None = None,
           now: datetime | None = None) -> list[Seat]:
    """Every known seat, whether or not a key or CLI is present."""
    now = now or datetime.now().astimezone()
    out_until = out_until or {}
    seats: list[Seat] = []
    for name in CLI_SEATS:
        b = backends.get(name)
        available = bool(b and b.available())
        status, until = _status(name, available, out_until, now)
        trains = bool(b and getattr(b, "trains_on_data", False))
        seats.append(Seat(name, "cli", status, until, trains))
    for name in HTTP_SEATS:
        b = backends.get(name)
        available = bool(b and b.available())
        status, until = _status(name, available, out_until, now)
        trains = bool(b and getattr(b, "trains_on_data", False))
        seats.append(Seat(name, "http", status, until, trains))
    return seats


def ready(seats: list[Seat]) -> bool:
    """Minimum CLI crew is seated (or marked out, so we don't wait forever).
    All three out is not ready: nobody is on the floor."""
    by_name = {s.name: s for s in seats}
    seated = 0
    for name in MINIMUM_CLI:
        seat = by_name.get(name)
        if seat is None or seat.status == "empty":
            return False
        seated += seat.status == "seated"
    return seated > 0


BULK_ORDER = ("groq", "mistral", "cloudflare", "zai", "gemini-api")
JOB_ORDER = {
    "edit": ("codex", "claude"),
    "decide": ("claude", "grok", "codex"),
    "review": ("claude", "grok", "codex"),
}
JOB_KINDS = ("bulk", "edit", "decide", "review")


def auth_failed(log_path: Path | None) -> set[str]:
    """Backends whose latest run in log.jsonl failed on login (401/403).
    Only steers `suggest`; the seat is not marked out (Phil fixes the key)."""
    from . import failures, runlog
    if log_path is None:
        return set()
    latest: dict[str, dict] = {}
    for record in runlog.read(Path(log_path)):
        latest[str(record["backend"])] = record  # file order: last line wins
    broken = set()
    for name, record in latest.items():
        reason = record.get("rejected")
        if record.get("ok") or not isinstance(reason, str) or not reason.startswith("failed"):
            continue
        failure = failures.classify(name, reason)
        if failure is not None and failure.kind == "auth":
            broken.add(name)
    return broken


def suggest_seat(job_kind: str, seats: list[Seat],
                 skip: set[str] | frozenset[str] = frozenset()) -> str | None:
    """Conductor: which seated model should take this kind of job.
    Skips empty, out, and `skip` (latest run failed auth, see auth_failed)."""
    seated = {s.name: s for s in seats if s.status == "seated" and s.name not in skip}
    if job_kind == "bulk":
        http = [s.name for s in seats if s.name in seated and s.kind == "http"]
        order = [n for n in BULK_ORDER if n in http] + [n for n in http if n not in BULK_ORDER]
        return order[0] if order else None
    for name in JOB_ORDER.get(job_kind, ()):
        if name in seated:
            return name
    return None


def format_roster(seats: list[Seat]) -> str:
    flag = "yes" if ready(seats) else "no — seat the missing CLI windows"
    lines = ["Hive floor", f"ready: {flag}", ""]
    lines.extend(s.line() for s in seats)
    lines.append("")
    lines.append("One window each for claude, codex, grok (gemini when its week is back).")
    lines.append("HTTP seats have no window; they wait in this Hive.")
    lines.append("Phil assigns work here. Subagents stay inside their CLI.")
    return "\n".join(lines)


def snapshot_path(home: Path | None = None) -> Path:
    return (home or config.HOME) / "floor.json"


def save_snapshot(seats: list[Seat], home: Path | None = None) -> Path:
    import json
    from .filelock import write_atomic
    path = snapshot_path(home)
    payload = {
        "ready": ready(seats),
        "seats": [
            {"name": s.name, "kind": s.kind, "status": s.status,
             "until": s.until.isoformat() if s.until else None,
             "trains_on_data": s.trains_on_data}
            for s in seats
        ],
    }
    write_atomic(path, json.dumps(payload, indent=2) + "\n")  # readers never see half a file
    return path


def introduce_text(seats: list[Seat]) -> str:
    """No @names: a mention would wake every bot if someone hits Start."""
    seated = [s.name for s in seats if s.status == "seated"]
    empty = [s.name for s in seats if s.status == "empty"]
    out = [s.name for s in seats if s.status == "out"]
    lines = [
        "Floor is up. One of each main CLI; HTTP models already have seats.",
        "Wait here for Phil. He says what to decide and what to do.",
        "Conserve Claude/Codex/Grok: bulk goes to Groq and the other HTTP seats.",
        f"Seated: {', '.join(seated) or 'none'}.",
    ]
    if out:
        lines.append(f"Out: {', '.join(out)}.")
    if empty:
        lines.append(f"Empty (need a key or install): {', '.join(empty)}.")
    return "\n".join(lines)


def format_msg(msg) -> str:
    return f"[{msg.author}] {msg.text}"


def peek_text(room_name: str, n: int = 10, home: Path | None = None) -> str:
    from . import room
    msgs = room.read_messages(room_name, home)
    if not msgs:
        return "(hive empty)\n(after=0)"
    lines = [format_msg(m) for m in msgs[-n:]] if n > 0 else []  # -n 0: cursor only
    return "\n".join(lines + [f"(after={len(msgs)})"])


def wait_for(room_name: str, home: Path | None = None, after: int | None = None,
             timeout: float = 120, pause: float = 0.25) -> list:
    """Block until hive has more than `after` messages. after=None means current count."""
    from . import room
    msgs = room.read_messages(room_name, home)
    baseline = len(msgs) if after is None else after
    if len(msgs) > baseline:
        return msgs[baseline:]
    deadline = monotonic() + max(0.0, timeout)
    while monotonic() < deadline:
        sleep(pause)
        msgs = room.read_messages(room_name, home)
        if len(msgs) > baseline:
            return msgs[baseline:]
    return []


def command(args, backends: dict[str, Backend], cfg: config.Config,
            write: Callable[[str], None] = print) -> int:
    from . import room
    action = getattr(args, "action", None) or "status"
    room_name = getattr(args, "room", None)
    if room_name is None:
        room_name = "hive"
    if action in ("introduce", "peek", "wait"):
        try:
            room.room_path(room_name)
        except ValueError as e:
            write(f"floor: {e}")
            return 2
    seats = roster(backends, cfg.out_until)
    if action in ("status", "introduce"):  # peek/wait poll often; don't rewrite floor.json
        save_snapshot(seats)
    if action == "status":
        write(format_roster(seats))
        return 0
    if action == "introduce":
        text = introduce_text(seats)
        room.say(room_name, text, author="floor")
        write(format_roster(seats))
        return 0
    if action == "peek":
        n = getattr(args, "n", None)
        write(peek_text(room_name, n=10 if n is None else n))
        return 0
    if action == "wait":
        timeout = getattr(args, "timeout", None)
        timeout = 120.0 if timeout is None else float(timeout)
        after = getattr(args, "after", None)
        if after is None:
            after = len(room.read_messages(room_name))
        after = max(0, after)
        new = wait_for(room_name, after=after, timeout=timeout)
        if not new:
            write(f"(no new hive message)\n(after={after})")
            return 1
        write("\n".join([format_msg(m) for m in new] + [f"(after={after + len(new)})"]))
        return 0
    if action == "suggest":
        kind = getattr(args, "kind", None)
        if kind not in JOB_KINDS:
            write("Usage: megazword floor suggest bulk|edit|decide|review")
            return 2
        name = suggest_seat(kind, seats, auth_failed(getattr(cfg, "log_path", None)))
        if name is None:
            write("(no seat)")
            return 1
        write(name)
        return 0
    write("Usage: megazword floor [status|introduce|peek|wait|suggest]")
    return 2
