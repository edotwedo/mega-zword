"""Read each AI plan's current usage meter without spending usage.

- Claude: asks Anthropic's usage endpoint with the login Claude Code already
  saved (~/.claude/.credentials.json). Unofficial endpoint, read-only. The
  token is only sent to api.anthropic.com and never printed or logged.
- Codex: asks Codex's own app server for its live rate limits
  (`account/rateLimits/read`, no model call). Falls back to the snapshot Codex
  writes into its session logs (~/.codex/sessions), as fresh as the last run.
- Grok: reads the billing line the Grok CLI logs when it fetches its credits
  (~/.grok/logs/unified.jsonl: weekly creditUsagePercent). Without it, reports
  Mega Zword's own recent run counts.
- Gemini: asks the Antigravity CLI (`agy -p /usage --output-format json`, its
  quota panel; reads, never prompts a model). Without agy, reports Mega
  Zword's own recent run counts.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path.home()


@dataclass
class Window:
    name: str          # e.g. "5-hour", "weekly"
    used_percent: float
    resets_at: datetime | None


@dataclass
class PlanUsage:
    service: str
    windows: list[Window]
    source: str
    note: str = ""
    as_of: datetime | None = None  # when the numbers were true (None = just now)


def _ts(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def claude() -> PlanUsage:
    creds = json.loads((HOME / ".claude" / ".credentials.json").read_text(encoding="utf-8"))
    token = creds["claudeAiOauth"]["accessToken"]
    req = urllib.request.Request(
        "https://api.anthropic.com/api/oauth/usage",
        headers={"Authorization": f"Bearer {token}",
                 "anthropic-beta": "oauth-2025-04-20",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    names = {"five_hour": "5-hour", "seven_day": "weekly",
             "seven_day_opus": "weekly (Opus)", "seven_day_sonnet": "weekly (Sonnet)"}
    windows = [
        Window(names.get(key, key), float(val.get("utilization") or 0), _ts(val.get("resets_at")))
        for key, val in data.items()
        if isinstance(val, dict) and "utilization" in val
    ]
    return PlanUsage("claude", windows, "anthropic usage endpoint")


def _window_label(mins) -> str:
    mins = int(mins or 0)
    return "weekly" if mins >= 10080 else f"{mins // 60}-hour"


def _codex_cmd() -> list[str] | None:
    import shutil
    exe = shutil.which("codex")
    return [exe, "app-server"] if exe else None


def codex_live(timeout: float = 15) -> PlanUsage | None:
    """Ask Codex's own app server (`codex app-server`, JSON-RPC on stdio) for
    `account/rateLimits/read`: the live plan meter, no model call, under a
    second. None when Codex isn't installed or doesn't answer in time."""
    cmd = _codex_cmd()
    if not cmd:
        return None
    import subprocess
    import threading
    from .backends import _kill_tree, process_group
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                            errors="replace", **process_group())
    timer = threading.Timer(timeout, _kill_tree, args=(proc, False))
    timer.start()
    try:
        for msg in ({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"clientInfo": {"name": "megazword", "version": "1"}}},
                    {"jsonrpc": "2.0", "method": "initialized"},
                    {"jsonrpc": "2.0", "id": 2, "method": "account/rateLimits/read"}):
            proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()
        for line in proc.stdout:  # ends when the timer kills a silent server
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("id") == 2:
                limits = (msg.get("result") or {}).get("rateLimits") or {}
                windows = [Window(_window_label(w.get("windowDurationMins")),
                                  float(w.get("usedPercent") or 0), _ts(w.get("resetsAt")))
                           for w in (limits.get("primary"), limits.get("secondary")) if w]
                return PlanUsage("codex", windows, "codex app-server (live)") if windows else None
        return None
    finally:
        timer.cancel()
        _kill_tree(proc, reap=False)


def codex() -> PlanUsage:
    try:
        live = codex_live()
    except (OSError, ValueError):
        live = None
    if live:
        return live
    logs = sorted((HOME / ".codex" / "sessions").rglob("*.jsonl"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    for path in logs[:20]:
        for line in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()):
            if '"rate_limits"' not in line:
                continue
            limits = _find_key(json.loads(line), "rate_limits")
            if not limits:
                continue
            windows = []
            for key in ("primary", "secondary"):
                w = limits.get(key)
                if w:
                    mins = w.get("window_minutes") or 0
                    label = "weekly" if mins >= 10080 else f"{mins // 60}-hour"
                    windows.append(Window(label, float(w.get("used_percent") or 0),
                                          _ts(w.get("resets_at"))))
            if not windows:
                # e.g. a run that failed on its usage limit logs an empty
                # snapshot; keep looking for the last real one.
                continue
            seen = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            return PlanUsage("codex", windows, "codex session log",
                             note=f"as of last Codex run ({seen.astimezone():%a %I:%M %p})",
                             as_of=seen)
    return PlanUsage("codex", [], "codex session log", note="no rate-limit data found yet")


GROK_BILLING_MSG = "billing: fetched credits config"


def grok_billing(now: datetime | None = None) -> PlanUsage | None:
    """Grok's plan meter from the billing line the Grok CLI logs each time it
    fetches its credits (~/.grok/logs/unified.jsonl): creditUsagePercent and the
    weekly period. Reads only the end of the log. None when no line is found."""
    path = HOME / ".grok" / "logs" / "unified.jsonl"
    if not path.is_file():
        return None
    with path.open("rb") as f:
        f.seek(max(0, path.stat().st_size - 4_000_000))
        tail = f.read().decode("utf-8", errors="replace").splitlines()
    for line in reversed(tail):
        if GROK_BILLING_MSG not in line:
            continue
        try:
            entry = json.loads(line)
            cfg = entry["ctx"]["config"]
            used = float(cfg["creditUsagePercent"])
            end = _ts(cfg.get("billingPeriodEnd") or cfg["currentPeriod"]["end"])
            seen = _ts(entry["ts"])
        except (ValueError, KeyError, TypeError):
            continue
        now = now or datetime.now(timezone.utc)
        if end and now >= end:
            # The week rolled over after this reading; Grok hasn't fetched the
            # new one yet (it does when it next runs), so don't show stale use.
            nxt = end
            while nxt <= now:
                nxt += timedelta(days=7)
            return PlanUsage("grok", [Window("weekly", 0.0, nxt)], "grok billing log",
                             note=f"new week since {end.astimezone():%a %I:%M %p}; "
                                  "exact use shows after Grok's next run")
        return PlanUsage("grok", [Window("weekly", used, end)], "grok billing log",
                         note=f"as of Grok's last check ({seen.astimezone():%a %I:%M %p})",
                         as_of=seen)
    return None


def grok(log_path: Path | None = None) -> PlanUsage:
    billing = grok_billing()
    if billing:
        return billing
    if log_path is None:
        from . import config
        log_path = config.HOME / "log.jsonl"
    from .runlog import summarize
    now = datetime.now(timezone.utc)
    recent = summarize(log_path, timedelta(hours=5), now).get("grok")
    weekly = summarize(log_path, timedelta(days=7), now).get("grok")
    return PlanUsage("grok", [], "Mega Zword run log",
                     note=f"no plan meter; Mega Zword sent {recent.runs if recent else 0} runs "
                          f"in the last 5h, {weekly.runs if weekly else 0} this week")


def _agy_window(raw: str) -> str:
    """Map an agy bucket window ("5h", "weekly", ...) to our window names."""
    text = str(raw or "").lower().replace(" ", "").replace("-", "")
    if text in ("5h", "5hour", "5hours", "fivehour"):
        return "5-hour"
    if text.startswith("week") or text in ("7d", "7day", "7days"):
        return "weekly"
    return str(raw or "unknown")


def parse_agy_usage(data: dict) -> list[Window]:
    """Turn agy's /usage JSON (command.data.groups[].buckets[] with
    remaining_fraction 0..1 and reset_time) into windows. Only the Gemini
    group counts toward the meter (it's what `-m gemini` spends); other groups
    (Claude/GPT models inside Antigravity) get names pacing ignores."""
    groups = ((data.get("command") or {}).get("data") or {}).get("groups") or []
    windows = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        gname = str(group.get("name") or "")
        is_gemini = "gemini" in gname.lower()
        for bucket in group.get("buckets") or []:
            if not isinstance(bucket, dict) or bucket.get("remaining_fraction") is None:
                continue
            used = max(0.0, min(100.0, (1 - float(bucket["remaining_fraction"])) * 100))
            name = _agy_window(bucket.get("window") or bucket.get("id"))
            if not is_gemini:
                name = f"{gname or 'other'}: {name}"
            windows.append(Window(name, used, _ts(bucket.get("reset_time"))))
    return windows


def _agy_path() -> str | None:
    import shutil
    return shutil.which("agy")


def gemini(log_path: Path | None = None) -> PlanUsage:
    agy = _agy_path()
    if agy:
        from .backends import run_quick
        # --print-timeout: without it agy can quit before Google's quota server answers.
        proc = run_quick([agy, "-p", "/usage", "--output-format", "json", "--print-timeout", "45s"],
                         timeout=60)
        if proc.returncode != 0:
            raise RuntimeError(f"agy /usage exited {proc.returncode}: "
                               f"{(proc.stderr or proc.stdout).strip()[-200:]}")
        windows = parse_agy_usage(json.loads(proc.stdout))
        return PlanUsage("gemini", windows, "agy /usage",
                         note="" if windows else "agy /usage returned no quota buckets")
    if log_path is None:
        from . import config
        log_path = config.HOME / "log.jsonl"
    from .runlog import summarize
    now = datetime.now(timezone.utc)
    recent = summarize(log_path, timedelta(hours=5), now).get("gemini")
    weekly = summarize(log_path, timedelta(days=7), now).get("gemini")
    return PlanUsage("gemini", [], "Mega Zword run log",
                     note=f"plan usage not tracked yet; Mega Zword sent {recent.runs if recent else 0} runs "
                          f"in the last 5h, {weekly.runs if weekly else 0} this week")


def _find_key(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            found = _find_key(v, key)
            if found:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find_key(v, key)
            if found:
                return found
    return None


SOURCES = {"claude": claude, "codex": codex}


def all_usage(log_path: Path | None = None) -> list[PlanUsage]:
    out = []
    for name, fn in SOURCES.items():
        try:
            out.append(fn())
        except Exception as exc:
            out.append(PlanUsage(name, [], "error", note=f"{type(exc).__name__}: {exc}"))
    for name, fn in (("grok", grok), ("gemini", gemini)):
        try:
            out.append(fn(log_path))
        except Exception as exc:
            out.append(PlanUsage(name, [], "error", note=f"{type(exc).__name__}: {exc}"))
    return out
