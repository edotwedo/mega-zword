"""Read each AI plan's current usage meter without spending usage.

- Claude: asks Anthropic's usage endpoint with the login Claude Code already
  saved (~/.claude/.credentials.json). Unofficial endpoint, read-only. The
  token is only sent to api.anthropic.com and never printed or logged.
- Codex: reads the rate-limit snapshot Codex writes into its own session logs
  (~/.codex/sessions). As fresh as the last Codex run.
- Grok: no local plan meter exists; reports Mega Zword's own recent run counts.
- Gemini: plan usage not tracked yet; reports Mega Zword's own recent run counts.
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


def codex() -> PlanUsage:
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
            seen = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            return PlanUsage("codex", windows, "codex session log",
                             note=f"as of last Codex run ({seen.astimezone():%a %I:%M %p})")
    return PlanUsage("codex", [], "codex session log", note="no rate-limit data found yet")


def grok(log_path: Path | None = None) -> PlanUsage:
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


def gemini(log_path: Path | None = None) -> PlanUsage:
    """No verified local quota source; these counts cover only our own runs."""
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
