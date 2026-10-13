"""Hive floor: one seat per model we can run. HTTP backends sit without a window."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
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
    """Minimum CLI crew is seated (or marked out, so we don't wait forever)."""
    by_name = {s.name: s for s in seats}
    for name in MINIMUM_CLI:
        seat = by_name.get(name)
        if seat is None or seat.status == "empty":
            return False
    return True


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
    path = snapshot_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ready": ready(seats),
        "seats": [
            {"name": s.name, "kind": s.kind, "status": s.status,
             "until": s.until.isoformat() if s.until else None,
             "trains_on_data": s.trains_on_data}
            for s in seats
        ],
    }
    path.write_text(__import__("json").dumps(payload, indent=2) + "\n", encoding="utf-8")
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
    return " ".join(lines) if False else "\n".join(lines)


def command(args, backends: dict[str, Backend], cfg: config.Config,
            write: Callable[[str], None] = print) -> int:
    from . import room
    seats = roster(backends, cfg.out_until)
    save_snapshot(seats)
    action = getattr(args, "action", None) or "status"
    if action == "status":
        write(format_roster(seats))
        return 0
    if action == "introduce":
        room_name = getattr(args, "room", None) or "hive"
        text = introduce_text(seats)
        room.say(room_name, text, author="floor")
        write(format_roster(seats))
        return 0
    write("Usage: megazword floor [status|introduce]")
    return 2
