#!/usr/bin/env python3
"""Read-only Hive snapshot. Run from any worktree; no megazword imports needed."""

import json
import os
import subprocess
from collections import deque
from datetime import datetime, timezone
from pathlib import Path


def compact(value, width=110):
    """Keep records on one line, including untrusted log/room text."""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=True)
    text = " ".join(str(value).split())
    text = "".join(c for c in text if c.isprintable())
    return text if len(text) <= width else text[:width - 3] + "..."


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def tail(path):
    try:
        with path.open(encoding="utf-8", errors="replace") as stream:
            return list(deque(stream, maxlen=5))
    except OSError:
        return []


def task_path():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip()) / "megazword-tasks.json"
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def show_tasks():
    print("OPEN TASKS")
    print(f"{'ID':14} {'SEAT':20} {'STATE':8} LEASE EXPIRY (UTC)")
    path = task_path()
    registry = read_json(path) if path else None
    tasks = registry.get("tasks", {}) if isinstance(registry, dict) else {}
    rows = tasks.values() if isinstance(tasks, dict) else []
    found = False
    now = datetime.now(timezone.utc)
    for task in rows:
        if not isinstance(task, dict) or task.get("state") != "open":
            continue
        found = True
        expiry = task.get("expires_at")
        try:
            stamp = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            stamp = stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp
            lease = stamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            if stamp <= now:
                lease += " EXPIRED"
        except (AttributeError, TypeError, ValueError, OverflowError):
            lease = "(unknown)"
        print(f"{compact(task.get('id', '?'), 14):14} "
              f"{compact(task.get('seat', '?'), 20):20} open     {lease}")
    if not found:
        print("(none)")


def main():
    home = Path(os.environ.get("MEGAZWORD_HOME", Path.home() / ".megazword")).expanduser()
    show_tasks()
    print("\nNIGHT DRIVER")
    state = read_json(home / "night" / "local-state.json")
    if isinstance(state, dict) and state:
        for job, detail in state.items():
            print(compact(f"{job}: {compact(detail)}"))
    else:
        print("(none)")
    print("NIGHT LOG (last 5)")
    for line in tail(home / "night" / "local.log") or ["(none)"]:
        print(compact(line))
    print("\nGUARD VERDICTS")
    guard = read_json(home / "guard.json")
    plans = guard.get("plans", []) if isinstance(guard, dict) else []
    plans = [p for p in plans if isinstance(p, dict)] if isinstance(plans, list) else []
    for plan in plans:
        print(compact(f"{plan.get('service', '?')}: {plan.get('verdict', '?')}"))
    if not plans:
        print("(none)")
    print("\nHIVE ROOM (last 5)")
    for line in tail(home / "rooms" / "hive.jsonl") or ["(none)"]:
        try:
            message = json.loads(line)
        except ValueError:
            message = None
        if isinstance(message, dict):
            print(compact(f"{message.get('time', '?')} {message.get('author', '?')}: "
                          f"{message.get('text', '')}"))
        else:
            print(compact(line))


if __name__ == "__main__":
    main()
