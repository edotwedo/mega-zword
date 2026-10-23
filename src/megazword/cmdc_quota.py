"""Read Command Code's supported /usage panel in a private Windows terminal.

No model prompt, credential parsing, provider HTTP requests, visible window, or
session transcript. Only parsed quota fields are cached, never terminal output.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone

from .usage_sources import PlanUsage, Window

CACHE_SECONDS = 120
TIMEOUT = 25
_ANSI = re.compile(r"\x1b\][\s\S]*?(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]")


def parse_screen(screen: str, now: datetime) -> PlanUsage:
    """Accept both displayed windows; never derive credits from token spend."""
    text = _ANSI.sub("", screen).replace("\r", "")
    found = {}
    rounded = False
    for match in re.finditer(r"(?mi)^\s*(5-hour|weekly)\s+[^\n]*?(\d+(?:\.\d+)?)%([^\n]*)", text):
        name, raw, tail = match.groups()
        used = float(raw)
        if not 0 <= used <= 100:
            raise ValueError("invalid cmdc quota percentage")
        duration = re.search(r"resets in\s+((?:\d+\s*[dhms]\s*)+)", tail, re.I)
        reset = None
        if duration:
            seconds = sum(int(n) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[unit.lower()]
                          for n, unit in re.findall(r"(\d+)\s*([dhms])", duration[1], re.I))
            reset = now + timedelta(seconds=seconds)
            rounded = True
        name = "weekly" if name.lower() == "weekly" else "5-hour"
        found[name] = Window(name, used, reset)
    if set(found) != {"5-hour", "weekly"}:
        raise ValueError("cmdc /usage did not show both quota windows")
    labels = re.findall(r"\b([A-Za-z0-9 +×-]{1,35} Plan)\s*[·|]", text)
    head = text.rsplit("Usage limits", 1)[0]
    monthly = re.findall(r"\b(\d+(?:\.\d+)?)%\s+used\b", head)
    notes = [re.sub(r"^USAGE\s+", "", labels[-1].strip())] if labels else []
    windows = [found["5-hour"], found["weekly"]]
    # The monthly window is a real budget, not just a note: the guard paces the renewal
    # off it. Its reset comes from "N days to renew" (None when the panel omits it).
    if monthly and 0 <= float(monthly[-1]) <= 100:
        used = float(monthly[-1])
        # The panel phrases this two ways; accept both, and leave the reset unknown
        # (rather than guessed) when neither matches.
        renew = (re.search(r"(\d+)\s*days?\s+to\s+renew(?:al)?", head, re.I)
                 or re.search(r"renew(?:al|s)?\s+in\s+(\d+)\s*days?", head, re.I))
        reset = now + timedelta(days=int(renew.group(1))) if renew else None
        windows.append(Window("monthly", used, reset))
        notes.append(f"monthly {used:g}% used")
    if rounded:
        notes.append("reset times rounded by CLI")
    return PlanUsage("cmdc", windows, "cmdc /usage", note="; ".join(notes), as_of=now)


def _command() -> list[str] | None:
    if sys.platform != "win32" or os.environ.get("MEGAZWORD_NO_CMDC_METER") == "1":
        return None
    shim, node = shutil.which("cmdc.cmd"), shutil.which("node.exe")
    if not shim or not node:
        return None
    # npm's official shim launches this entry point. Running Node directly
    # also lets us terminate exactly this probe, without an intermediate shell.
    entry = Path(shim).parent / "node_modules" / "command-code" / "dist" / "index.mjs"
    if not entry.is_file():
        return None
    return [node, str(entry), "--no-auto-update", "--no-session", "--skip-onboarding",
            "--trust", "--safe-mode", "--no-skills"]


def _capture(command: list[str]) -> str:
    from winpty import PtyProcess  # optional workspace dependency

    env = os.environ.copy()
    for name in ("MEGAZWORD_SEAT", "MEGAZWORD_SESSION", "CODEX_THREAD_ID", "MEGAZWORD_CLIENT"):
        env.pop(name, None)
    env["TERM"] = "xterm-256color"
    chunks: list[str] = []
    guard = threading.Lock()
    with tempfile.TemporaryDirectory(prefix="mz-cmdc-quota-") as cwd:
        proc = PtyProcess.spawn(command, cwd=cwd, env=env, dimensions=(55, 140))

        def read():
            try:
                while proc.isalive():
                    part = proc.read(65536)
                    with guard:
                        chunks.append(part)
                        if sum(map(len, chunks)) > 200_000:
                            return
                    if "\x1b[6n" in part:
                        proc.write("\x1b[1;1R")
                    if "\x1b[c" in part or "\x1b[0c" in part:
                        proc.write("\x1b[?1;2c")
            except Exception:
                pass

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        sent = False
        deadline = time.monotonic() + TIMEOUT
        try:
            while time.monotonic() < deadline:
                with guard:
                    screen = "".join(chunks)
                if len(screen) > 200_000:
                    raise ValueError("cmdc quota output exceeded limit")
                if not sent and "Ask your question" in _ANSI.sub("", screen):
                    # A fixed, locally handled slash command; never accept a task
                    # string here or fall back to a model prompt.
                    # The prompt can paint before its input listeners bind;
                    # allow startup and slash completion to settle separately.
                    time.sleep(1)
                    proc.write("/usage")
                    time.sleep(1)
                    proc.write("\r")
                    sent = True
                if sent:
                    try:
                        parse_screen(screen, datetime.now(timezone.utc))
                        return screen
                    except ValueError:
                        pass
                if not proc.isalive():
                    break
                time.sleep(.1)
            raise TimeoutError("cmdc quota panel unavailable")
        finally:
            proc.terminate(force=True)
            reader.join(timeout=1)


def _cached(path: Path, now: datetime) -> PlanUsage | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        stamp = datetime.fromisoformat(data["as_of"])
        if not timedelta(0) <= now - stamp <= timedelta(hours=1):
            return None
        windows = [Window(w["name"], float(w["used_percent"]),
                          datetime.fromisoformat(w["resets_at"]) if w["resets_at"] else None)
                   for w in data["windows"]]
        if {w.name for w in windows} not in ({"5-hour", "weekly"},
                                             {"5-hour", "weekly", "monthly"}) or any(
                not 0 <= w.used_percent <= 100 or (w.resets_at and w.resets_at <= now)
                for w in windows):
            return None
        return PlanUsage("cmdc", windows, "cmdc /usage", note=str(data.get("note", "")), as_of=stamp)
    except (OSError, ValueError, TypeError, KeyError):
        return None


def read_quota(now: datetime | None = None) -> PlanUsage | None:
    from . import config
    from .filelock import locked, write_atomic

    now = now or datetime.now(timezone.utc)
    path = config.HOME / "meter_cache_cmdc.json"
    cached = _cached(path, now)
    if cached and (now - cached.as_of).total_seconds() < CACHE_SECONDS:
        return cached
    command = _command()
    if not command:
        return cached
    try:
        with locked(path, timeout=1) as acquired:
            if not acquired:
                return cached
            latest = _cached(path, now)
            if latest and (now - latest.as_of).total_seconds() < CACHE_SECONDS:
                return latest
            # Timestamp when the panel was read, not before CLI startup.
            plan = parse_screen(_capture(command), datetime.now(timezone.utc))
            write_atomic(path, json.dumps({
                "as_of": plan.as_of.isoformat(), "note": plan.note,
                "windows": [{"name": w.name, "used_percent": w.used_percent,
                             "resets_at": w.resets_at.isoformat() if w.resets_at else None}
                            for w in plan.windows],
            }))
            return plan
    except (OSError, ImportError, ValueError, TimeoutError, RuntimeError):
        if cached:
            cached.note += "; refresh unavailable, last CLI reading"
        return cached
