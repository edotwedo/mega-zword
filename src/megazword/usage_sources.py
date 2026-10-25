"""Read each AI plan's current usage meter without spending usage.

- Claude: OFF by default. It can read the login Claude Code saved
  (~/.claude/.credentials.json) and ask Anthropic's unofficial usage endpoint,
  but that is a terms-of-service risk for a shipped product and for the user's
  own account. Set MEGAZWORD_CLAUDE_METER=1 to enable it on your own machine;
  otherwise Claude's window is left empty rather than reading credentials.
- Codex: asks Codex's own app server for its live rate limits
  (`account/rateLimits/read`, no model call). Falls back to the snapshot Codex
  writes into its session logs (~/.codex/sessions), as fresh as the last run.
- Grok: reads the billing line the Grok CLI logs when it fetches its credits
  (~/.grok/logs/unified.jsonl: weekly creditUsagePercent). Without it, reports
  Mega Zword's own recent run counts.
- Gemini: asks the Antigravity CLI (`agy -p /usage --output-format json`, its
  quota panel; reads, never prompts a model). Without agy, reports Mega
  Zword's own recent run counts.
- Command Code: reads its supported /usage panel in a private Windows terminal
  (no model prompt or credential parsing), caching quota fields for two minutes.
  Falls back to local transcript spend; dollars are not remaining plan credits.
"""

from __future__ import annotations

import json
import os
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


CLAUDE_CACHE_SECONDS = 120  # the endpoint answers 429 when polled too often


def _claude_cache() -> Path:
    from . import config
    return config.HOME / "meter_cache_claude.json"


def claude() -> PlanUsage:
    """Claude's meter, shared through a small cache file so the status bar,
    widget, dashboard and CLI together ask Anthropic at most every 2 minutes.
    On HTTP 429 the last good reading is shown with its time instead.

    Disabled unless MEGAZWORD_CLAUDE_METER=1: reading ~/.claude credentials and
    calling the unofficial usage endpoint breaks Anthropic's terms for a third
    party, so a shipped build must never do it."""
    if os.environ.get("MEGAZWORD_CLAUDE_METER") != "1":
        return PlanUsage("claude", [], "meter off (unofficial endpoint)",
                         note="set MEGAZWORD_CLAUDE_METER=1 to read your own plan; "
                              "shipped builds must not read Claude credentials")
    import urllib.error
    cache, now = _claude_cache(), datetime.now(timezone.utc)
    cached = None
    try:
        cached = json.loads(cache.read_text(encoding="utf-8"))
        age = (now - _ts(cached["at"])).total_seconds()
        if 0 <= age < CLAUDE_CACHE_SECONDS:
            return _claude_plan(cached["data"])
    except (OSError, ValueError, KeyError, TypeError):
        cached = None
    creds = json.loads((HOME / ".claude" / ".credentials.json").read_text(encoding="utf-8"))
    token = creds["claudeAiOauth"]["accessToken"]
    req = urllib.request.Request(
        "https://api.anthropic.com/api/oauth/usage",
        headers={"Authorization": f"Bearer {token}",
                 "anthropic-beta": "oauth-2025-04-20",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 429 and cached:
            seen = _ts(cached["at"])
            plan = _claude_plan(cached["data"])
            plan.as_of, plan.note = seen, f"busy (429); last reading {seen.astimezone():%I:%M %p}"
            return plan
        raise
    try:
        # Atomic: the status bar, widget and dashboard read this file at the same time, and a
        # half-written one would cost an extra API call and lose the 429 fallback.
        from .filelock import write_atomic
        write_atomic(cache, json.dumps({"at": now.isoformat(), "data": data}))
    except OSError:
        pass
    return _claude_plan(data)


def _claude_plan(data: dict) -> PlanUsage:
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
                checked_at = datetime.now(timezone.utc)
                limits = (msg.get("result") or {}).get("rateLimits") or {}
                windows = [Window(_window_label(w.get("windowDurationMins")),
                                  float(w.get("usedPercent") or 0), _ts(w.get("resetsAt")))
                           for w in (limits.get("primary"), limits.get("secondary")) if w]
                return PlanUsage("codex", windows, "codex app-server (live)",
                                 as_of=checked_at) if windows else None
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
        is_gemini = gname.strip().lower() == "gemini models"
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


COMMAND_CODE_ROOT = HOME / ".commandcode" / "projects"
CMDC_RECENT = timedelta(hours=5)
CMDC_WEEK = timedelta(days=7)


def _cmdc_transcripts(root: Path, since: datetime) -> list[Path]:
    """Transcripts touched since `since`. One file per session, in a folder per
    working directory (~/.commandcode/projects/<slug>/<session>.jsonl)."""
    if not root.is_dir():
        return []
    cutoff = since.timestamp()
    found = []
    for path in root.rglob("*.jsonl"):
        try:
            if path.stat().st_mtime >= cutoff:
                found.append(path)
        except OSError:
            continue
    return found


def _cmdc_spend(root: Path, since: datetime) -> tuple[int, float, int]:
    """(calls, dollars, tokens) Command Code recorded at or after `since`."""
    calls, cost, tokens = 0, 0.0, 0
    for path in _cmdc_transcripts(root, since):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            if '"usage"' not in line:  # skips the header and tool-only lines
                continue
            try:
                entry = json.loads(line)
                when = _ts(entry.get("timestamp"))
            except ValueError:
                continue
            if when is None or when < since:
                continue
            usage = entry.get("usage") or {}
            try:
                cost += float(usage.get("costUsd") or 0.0)
                tokens += int(usage.get("inputTokens") or 0) + int(usage.get("outputTokens") or 0)
            except (TypeError, ValueError):
                continue
            calls += 1
    return calls, cost, tokens


def _token_label(tokens: int) -> str:
    """Short human form; a week of 200k-token turns must not read as '196869k'."""
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.0f}M tok"
    return f"{tokens // 1000}k tok"


def command_code(projects_dir: Path | None = None,
                 now: datetime | None = None) -> PlanUsage:
    """Command Code's own spend, totalled from its local session transcripts.

    Every committed turn records the call's usage - inputTokens, outputTokens,
    cacheReadTokens, cacheWriteTokens and costUsd - plus the model it ran on, so
    the dollars are already on disk. Same trick the Codex fallback uses on
    ~/.codex/sessions: read the tool's own log, spend nothing to read it.

    Plan windows come from Command Code's own API first, then the /usage panel in a
    private terminal. Either is separate from transcript dollar totals: dollars are not
    plan credits. Explicit projects_dir calls only inspect those transcripts (offline use).
    """
    root = COMMAND_CODE_ROOT if projects_dir is None else projects_dir
    now = now or datetime.now(timezone.utc)
    from .cmdc_quota import read_api, read_quota
    quota = (read_api(now) or read_quota(now)) if projects_dir is None else None
    calls, cost, tokens = _cmdc_spend(root, now - CMDC_WEEK)
    if quota:
        if calls:
            quota.note += f"; logged ${cost:.2f}/7d, {_token_label(tokens)} (not plan credits)"
        return quota
    if not calls:
        return PlanUsage("cmdc", [], "command-code session logs",
                         note="no Command Code usage in the last 7 days")
    _, recent_cost, _ = _cmdc_spend(root, now - CMDC_RECENT)
    return PlanUsage(
        "cmdc", [], "command-code session logs",
        note=f"spent ${recent_cost:.2f}/5h, ${cost:.2f}/7d, {_token_label(tokens)}; no plan meter",
    )


SOURCES = {"claude": claude, "codex": codex, "cmdc": command_code}


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
