"""Sentinel collector: Windows and Linux reboots, logins and network changes.

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


def _is_windows() -> bool:
    """Tests patch this. Do not patch os.name: pathlib then becomes WindowsPath and Linux CI crashes."""
    return os.name == "nt"

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
    et, ct = str(event.get("time") or ""), str(cursor.get("time") or "")
    if et != ct:
        return et > ct
    try:  # a hand-edited or damaged cursor file must not stop collection
        return int(event.get("record_id") or 0) > int(cursor.get("record_id") or 0)
    except (TypeError, ValueError):
        return True


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
    if not _is_windows():
        return ""
    try:
        from .backends import no_window
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, **no_window())
    except subprocess.TimeoutExpired:  # callers handle OSError ("collect skipped")
        raise OSError("reading the event log took over 30s") from None
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
    try:
        data = json.loads(text)
    except ValueError:
        raise OSError(f"unreadable {channel} event log output") from None
    rows = data if isinstance(data, list) else [data]
    out = []
    for raw in rows:
        rec = _record(raw if isinstance(raw, dict) else {}, channel)
        if rec and _newer(rec, since):
            out.append(rec)
    out.sort(key=lambda r: (r["time"], r["record_id"]))
    return out


# Journal matches use '+' for OR across different fields.
LINUX_SOURCES = (
    ("journal:boot", (6005,)),
    ("journal:login", (4624, 4625, 4634)),
    ("journal:network", (10000, 10001)),
)
JOURNAL_FILTERS = {
    "journal:boot": ["_COMM=systemd", "_PID=1"],
    "journal:login": ["_COMM=systemd-logind", "+", "_COMM=sshd", "+", "_COMM=login"],
    "journal:network": ["_SYSTEMD_UNIT=NetworkManager.service", "+",
                        "_SYSTEMD_UNIT=systemd-networkd.service", "+", "_COMM=NetworkManager"],
}


def linux_reader(channel: str, ids: tuple[int, ...], since: dict | None) -> list[dict]:
    """Read a bounded slice of the current boot without a shell or extra packages."""
    import hashlib
    import re
    args = ["journalctl", "-b", "-o", "short-iso", "--no-pager", "-n", "200",
            *JOURNAL_FILTERS[channel]]
    if channel == "journal:boot":
        args += ["--grep=running in system mode|Startup finished"]
    try:
        result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=30)
    except subprocess.TimeoutExpired:
        raise OSError("reading the journal took over 30s") from None
    if result.returncode:
        raise OSError((result.stderr or result.stdout or "journalctl failed").strip()[:300])
    out = []
    for line in result.stdout.splitlines():
        match = re.match(r"^(\S+) \S+ ([^:]+): (.*)$", line)
        if not match:
            continue
        stamp, provider, message = match.groups()
        try:
            stamp = datetime.fromisoformat(stamp).astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
        lower = message.lower()
        event_id = None
        if channel == "journal:boot":
            if "running in system mode" in lower or "startup finished" in lower:
                event_id = 6005
        elif channel == "journal:login":
            if "failed password" in lower or "authentication failure" in lower:
                event_id = 4625
            elif "new session" in lower or "session opened" in lower or "accepted " in lower:
                event_id = 4624
            elif "removed session" in lower or "session closed" in lower:
                event_id = 4634
        else:
            if any(word in lower for word in ("disconnected", "deactivated", "link down", "lost carrier")):
                event_id = 10001
            elif any(word in lower for word in ("connected", "activated", "link up", "gained carrier", "dhcp", "configured")):
                event_id = 10000
        if event_id not in ids:
            continue
        record_id = int.from_bytes(hashlib.sha256(line.encode()).digest()[:8], "big")
        rec = _record({"time": stamp, "id": event_id, "provider": provider,
                       "message": message, "record_id": record_id}, channel)
        # short-iso has second precision. Keep all fingerprints at the boundary
        # rather than imposing an arbitrary order on events within that second.
        if since and (stamp < since["time"] or
                      (stamp == since["time"] and record_id in since.get("seen", []))):
            continue
        out.append(rec)
    out.sort(key=lambda r: (r["time"], r["record_id"]))
    return out


def collect(reader=None) -> list[dict]:
    """Append new events to sentinel.jsonl. `reader(channel, ids, since)`
    is injected in tests."""
    linux = reader is None and not _is_windows()
    reader = reader or (linux_reader if linux else windows_reader)
    cursor = _load_cursor()
    added: list[dict] = []
    security_ok = cursor.get("security_readable", True)
    for channel, ids in (LINUX_SOURCES if linux else SOURCES):
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
        if linux:
            seen = since.get("seen", []) if since and since["time"] == last["time"] else []
            cursor[channel]["seen"] = seen + [e["record_id"] for e in events
                                               if e["time"] == last["time"]]
    cursor["security_readable"] = security_ok
    if linux:
        added.sort(key=lambda r: (r["time"], r["record_id"]))
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
        "sites": [
            {"url": url, **row} for url, row in (_load_checks().get("sites") or {}).items()
            if isinstance(row, dict)
        ],
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
    ] + [
        f"{'site':16} {'ok' if row.get('ok') else 'DOWN'}  {row.get('url')}"
        for row in s.get("sites") or []
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


def checks_path() -> Path:
    return config.HOME / "sentinel.checks.json"


def _load_checks() -> dict:
    p = checks_path()
    if not p.exists():
        return {"sites": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"sites": {}}
    if not isinstance(data, dict) or not isinstance(data.get("sites"), dict):
        return {"sites": {}}
    return data


def _save_checks(data: dict) -> None:
    p = checks_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with locked(p):
        write_atomic(p, json.dumps(data, indent=2) + "\n")


def _http_get(url: str, timeout: int = 10, data: bytes | None = None,
              headers: dict | None = None) -> int:
    from urllib.request import Request, urlopen
    req = Request(url, data=data, method="POST" if data is not None else "GET",
                  headers={"User-Agent": "megazword-sentinel", **(headers or {})})
    with urlopen(req, timeout=timeout) as resp:
        return int(resp.status)


def probe(url: str, getter=None) -> bool:
    getter = getter or _http_get
    try:
        status = getter(url)
        return 200 <= int(status) < 400
    except (OSError, ValueError, TimeoutError):
        return False


def _ntfy(topic: str, title: str, body: str, getter=None) -> None:
    if not topic:
        return
    getter = getter or _http_get
    getter(f"https://ntfy.sh/{topic}", data=body.encode("utf-8"),
           headers={"Title": title})


def check_sites(cfg: config.Config | None = None, getter=None) -> dict:
    """One round of production URL checks. ntfy after two failures in a row
    and again on recovery. Always pings healthchecks.io when a URL is set."""
    cfg = cfg or config.load()
    getter = getter or _http_get
    state = _load_checks()
    sites = state.setdefault("sites", {})
    alerts: list[str] = []
    results = []
    for url in cfg.sentinel_urls:
        row = sites.get(url) if isinstance(sites.get(url), dict) else {}
        fails = int(row.get("fails") or 0)
        down = bool(row.get("down"))
        ok = probe(url, getter)
        if ok:
            if down:
                msg = f"back up: {url}"
                alerts.append(msg)
                try:
                    _ntfy(cfg.ntfy_topic, "Sentinel recovery", msg, getter)
                except (OSError, ValueError, TimeoutError):
                    pass
            fails, down = 0, False
        else:
            fails += 1
            if fails >= 2 and not down:
                down = True
                msg = f"down: {url} ({fails} failures)"
                alerts.append(msg)
                try:
                    _ntfy(cfg.ntfy_topic, "Sentinel down", msg, getter)
                except (OSError, ValueError, TimeoutError):
                    pass
        sites[url] = {"ok": ok, "fails": fails, "down": down,
                      "time": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        results.append({"url": url, "ok": ok, "fails": fails, "down": down})
    if cfg.healthchecks_url:
        try:
            getter(cfg.healthchecks_url)
            state["healthchecks"] = "ok"
        except (OSError, ValueError, TimeoutError):
            state["healthchecks"] = "failed"
    state["sites"] = sites
    _save_checks(state)
    return {"sites": results, "alerts": alerts,
            "healthchecks": state.get("healthchecks")}


def format_check(result: dict) -> str:
    lines = ["Sentinel checks"]
    for row in result.get("sites") or []:
        mark = "ok" if row.get("ok") else "DOWN"
        extra = f"  ({row['fails']} in a row)" if not row.get("ok") else ""
        lines.append(f"  {mark:4}  {row['url']}{extra}")
    hc = result.get("healthchecks")
    if hc:
        lines.append(f"  healthchecks.io  {hc}")
    for alert in result.get("alerts") or []:
        lines.append(f"  alert  {alert}")
    return "\n".join(lines)


def _install_linux(yes: bool) -> int:
    import sys
    directory = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "systemd/user"
    print(f"[megazword] user timer: {directory / 'megazword-sentinel.timer'} (every 5 minutes)")
    if not yes:
        print("[megazword] run `megazword sentinel install --yes` to create and enable the timer")
        return 0
    def quote(value):
        return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") + '"'
    service = ("[Unit]\nDescription=Mega Zword sentinel\n\n[Service]\nType=oneshot\n"
               f"ExecStart={quote(sys.executable)} -m megazword.cli sentinel check\n"
               f"WorkingDirectory={quote(Path(__file__).resolve().parents[2])}\n")
    timer = ("[Unit]\nDescription=Collect sentinel events every five minutes\n\n[Timer]\n"
             "OnStartupSec=1min\nOnUnitActiveSec=5min\n\n[Install]\nWantedBy=timers.target\n")
    try:
        directory.mkdir(parents=True, exist_ok=True)
        write_atomic(directory / "megazword-sentinel.service", service)
        write_atomic(directory / "megazword-sentinel.timer", timer)
        for args in (["systemctl", "--user", "daemon-reload"],
                     ["systemctl", "--user", "enable", "--now", "megazword-sentinel.timer"]):
            result = subprocess.run(args, capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise OSError((result.stderr or result.stdout).strip()[:300])
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"[megazword] user timer install failed: {exc}", file=sys.stderr)
        return 1
    print("[megazword] enabled megazword-sentinel.timer every 5 minutes and at user startup")
    return 0


def install(yes: bool = False) -> int:
    """Register a 5-minute scheduled task. Prints the plan; `--yes` creates it.
    Phil approves by passing --yes."""
    import secrets
    import sys
    path = config.HOME / "config.toml"
    cfg = config.load(path) if path.exists() else config.Config()
    topic = cfg.ntfy_topic
    if not topic:
        topic = "mz-" + secrets.token_urlsafe(12)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("[sentinel]\n", encoding="utf-8")
        config._set_key(path, "sentinel", "ntfy_topic", json.dumps(topic))
        print(f"[megazword] ntfy topic: {topic}  (saved in {path})")
    else:
        print(f"[megazword] ntfy topic already set in {path}")
    print("[megazword] subscribe to that topic in the ntfy app (no account).")
    print("[megazword] optional: set [sentinel] healthchecks_url to a healthchecks.io ping URL")
    if not _is_windows():
        return _install_linux(yes)
    # pythonw: no console window flashing up every 5 minutes.
    from .desktop import launcher_python
    cmd = f'"{launcher_python()}" -m megazword.cli sentinel check'
    print(f"[megazword] task command: {cmd}")
    if not yes:
        print("[megazword] run `megazword sentinel install --yes` to create the 5-minute task (Phil's call)")
        return 0
    create = [
        "schtasks", "/Create", "/TN", "MegaZword-Sentinel", "/SC", "MINUTE", "/MO", "5",
        "/TR", cmd, "/F",
    ]
    logon = [
        "schtasks", "/Create", "/TN", "MegaZword-Sentinel-Logon", "/SC", "ONLOGON",
        "/TR", cmd, "/F",
    ]
    for args in (create, logon):
        result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                                errors="replace",
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode != 0:
            print(f"[megazword] schtasks failed: {(result.stderr or result.stdout).strip()[:300]}",
                  file=sys.stderr)
            return 1
    print("[megazword] scheduled MegaZword-Sentinel every 5 minutes and at logon")
    return 0


def command(args) -> int:
    import sys
    action = getattr(args, "action", "status") or "status"
    if action == "log":
        print(format_log(max(1, getattr(args, "n", 20) or 20)))
        return 0
    if action == "install":
        return install(bool(getattr(args, "yes", False)))
    if action == "check":
        try:
            collect()
        except OSError as exc:
            print(f"[megazword] sentinel collect skipped: {exc}", file=sys.stderr)
        print(format_check(check_sites()))
        return 0
    try:
        collect()
    except OSError as exc:
        print(f"[megazword] sentinel collect skipped: {exc}", file=sys.stderr)
    print(format_status())
    return 0

