"""Sentinel collector: Windows reboots, logins and network changes.

Writes ~/.megazword/sentinel.jsonl. Tests inject a fake reader so they never
need admin or a real event log. Production URL checks are B9.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import config, log
from .filelock import locked, write_atomic

KEEP = 2000
MSG_CHARS = 300

# channel -> event ids (Kernel-Power 41 lives in the System log)
SOURCES = (
    ("System", (6005, 6006, 6008, 1074, 41)),
    ("Security", (4624, 4625, 4634, 4647)),
    ("Microsoft-Windows-NetworkProfile/Operational", (10000, 10001)),
)

KIND = {
    6005: "boot",
    6006: "shutdown",
    6008: "unexpected_shutdown",
    1074: "shutdown_request",
    41: "kernel_power",
    4624: "login",
    4625: "login_failed",
    4634: "logoff",
    4647: "logoff_user",
    10000: "network_up",
    10001: "network_down",
}


def path() -> Path:
    return config.HOME / "sentinel.jsonl"


def cursor_path() -> Path:
    return config.HOME / "sentinel.cursor.json"


def _load_cursor() -> dict:
    p = cursor_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_cursor(data: dict) -> None:
    p = cursor_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with locked(p):
        write_atomic(p, json.dumps(data, indent=2) + "\n")


def recent(n: int = 40) -> list[dict]:
    p = path()
    if not p.exists():
        return []
    with locked(p):
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    out = []
    for line in reversed(lines):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
        if len(out) >= n:
            break
    return out


def _newer(event: dict, cursor: dict | None) -> bool:
    if not cursor:
        return True
    et, ct = event.get("time") or "", cursor.get("time") or ""
    if et != ct:
        return et > ct
    return int(event.get("record_id") or 0) > int(cursor.get("record_id") or 0)


def _record(raw: dict, channel: str) -> dict | None:
    try:
        event_id = int(raw.get("id") or raw.get("Id") or 0)
    except (TypeError, ValueError):
        return None
    if event_id not in KIND:
        return None
    time = str(raw.get("time") or raw.get("TimeCreated") or "")
    if not time:
        return None
    try:
        record_id = int(raw.get("record_id") or raw.get("RecordId") or 0)
    except (TypeError, ValueError):
        record_id = 0
    msg = str(raw.get("message") or raw.get("Message") or "")[:MSG_CHARS]
    return {
        "time": time,
        "kind": KIND[event_id],
        "event_id": event_id,
        "channel": channel,
        "provider": str(raw.get("provider") or raw.get("ProviderName") or ""),
        "message": msg,
        "record_id": record_id,
    }


def _powershell(script: str) -> str:
    if os.name != "nt":
        return ""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "powershell failed").strip()
        raise OSError(err[:300])
    return result.stdout.strip()


def windows_reader(channel: str, ids: tuple[int, ...], since: dict | None) -> list[dict]:
    """Newest matching events from one Windows log. Raises OSError on
    access denied (typical for Security without Event Log Readers)."""
    id_list = ",".join(str(i) for i in ids)
    # ToUniversalTime + round-trip so we never depend on /Date(ms)/ JSON.
    script = (
        f"$h = @{{ LogName = '{channel}'; Id = @({id_list}) }}; "
        "Get-WinEvent -FilterHashtable $h -MaxEvents 200 -ErrorAction Stop | "
        "Select-Object @{n='time';e={$_.TimeCreated.ToUniversalTime().ToString('o')}}, "
        "@{n='id';e={$_.Id}}, @{n='provider';e={$_.ProviderName}}, "
        "@{n='record_id';e={$_.RecordId}}, @{n='message';e={$_.Message}} | "
        "ConvertTo-Json -Compress"
    )
    try:
        text = _powershell(script)
    except OSError as exc:
        if "No events" in str(exc) or "NoMatchingEvents" in str(exc):
            return []
        raise
    if not text:
        return []
    data = json.loads(text)
    rows = data if isinstance(data, list) else [data]
    out = []
    for raw in rows:
        rec = _record(raw if isinstance(raw, dict) else {}, channel)
        if rec and _newer(rec, since):
            out.append(rec)
    out.sort(key=lambda r: (r["time"], r["record_id"]))
    return out


def collect(reader=None) -> list[dict]:
    """Append new events to sentinel.jsonl. `reader(channel, ids, since)`
    is injected in tests."""
    reader = reader or windows_reader
    cursor = _load_cursor()
    added: list[dict] = []
    security_ok = cursor.get("security_readable", True)
    for channel, ids in SOURCES:
        since = cursor.get(channel) if isinstance(cursor.get(channel), dict) else None
        try:
            events = reader(channel, ids, since)
            if channel == "Security":
                security_ok = True
        except OSError:
            if channel == "Security":
                security_ok = False
                cursor["security_readable"] = False
                continue
            raise
        if not events:
            continue
        added.extend(events)
        last = events[-1]
        cursor[channel] = {"time": last["time"], "record_id": last["record_id"]}
    cursor["security_readable"] = security_ok
    if added:
        p = path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with locked(p):
            with p.open("a", encoding="utf-8") as f:
                for rec in added:
                    f.write(json.dumps(rec) + "\n")
            log.trim_unlocked(p, KEEP)
    _save_cursor(cursor)
    return added


def _last(kind_prefix: tuple[str, ...], events: list[dict]) -> dict | None:
    for row in events:
        if row.get("kind") in kind_prefix:
            return row
    return None


def summary(n: int = 12) -> dict:
    """Dashboard/status snapshot from the jsonl (does not collect)."""
    events = recent(200)
    today = datetime.now(timezone.utc).date().isoformat()
    boot = _last(("boot", "kernel_power", "unexpected_shutdown"), events)
    login = _last(("login", "login_failed", "logoff", "logoff_user"), events)
    net = _last(("network_up", "network_down"), events)
    cursor = _load_cursor()
    return {
        "last_boot": boot,
        "last_login": login,
        "last_network": net,
        "today": sum(1 for e in events if str(e.get("time") or "").startswith(today)),
        "security_readable": bool(cursor.get("security_readable", True)),
        "recent": events[:n],
        "count": len(events),
    }


def format_status() -> str:
    s = summary()
    def line(label, row):
        if not row:
            return f"{label:16} —"
        msg = (row.get("message") or "")[:60]
        return f"{label:16} {str(row.get('time') or '')[:19].replace('T', ' ')}  {row.get('kind')}  {msg}"
    sec = "readable" if s["security_readable"] else "needs Event Log Readers (one admin command)"
    return "\n".join([
        "Sentinel",
        line("last boot", s["last_boot"]),
        line("last login", s["last_login"]),
        line("last network", s["last_network"]),
        f"{'today':16} {s['today']} events",
        f"{'security log':16} {sec}",
    ])


def format_log(n: int = 20) -> str:
    rows = recent(n)
    if not rows:
        return "[megazword] no sentinel events yet; run `megazword sentinel status` to collect"
    lines = []
    for row in rows:
        t = str(row.get("time") or "")[:19].replace("T", " ")
        lines.append(f"{t}  {str(row.get('kind') or ''):20}  "
                     f"{row.get('channel')} {row.get('event_id')}  "
                     f"{(row.get('message') or '')[:80]}")
    return "\n".join(lines)


def command(args) -> int:
    import sys
    action = getattr(args, "action", "status") or "status"
    if action == "log":
        print(format_log(max(1, getattr(args, "n", 20) or 20)))
        return 0
    try:
        collect()
    except OSError as exc:
        print(f"[megazword] sentinel collect skipped: {exc}", file=sys.stderr)
    print(format_status())
    return 0
