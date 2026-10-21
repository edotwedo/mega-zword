"""Usage-first hook (Phil's rule): before any work, read every AI's live usage
and plan the labor from it. Claude Code runs this at session start ("start") and
on every prompt ("prompt"). Read-only: it prints hook JSON and never changes
anything. Never fails the session. One-time PC setup is a separate, explicit
command: `python scripts/install_usage_hook.py --yes`."""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

BOARD = "https://github.com/edotwedo/workshop/pull/33#issuecomment-6115098816"
RULE = ("USAGE FIRST (Phil's standing rule): before starting, claiming or handing out any work, "
        "read every AI's live usage and plan support from it; cmdc remains owner and assigns work. "
        "Lanes in STATUS.md or handoffs are a starting point, not a rule; re-plan "
        "whenever the reading changes. Quote the reading in your plan. On Phil's PC: "
        "`megazword startup` once (bounded usage and floor readings). Elsewhere: the usage board "
        f"in Q ({BOARD}); over 30 minutes old means the PC is asleep, so say so.")


def run(cmd, timeout):
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                         errors="replace", timeout=timeout)
    return (out.stdout or out.stderr).strip()


def find_megazword() -> str | None:
    """PATH first; else Phil's install (Claude Code's PATH on his PC doesn't include
    the venv, checked 2026-10-12)."""
    found = shutil.which("megazword")
    if found:
        return found
    venv = Path.home() / "mega-zword" / ".venv" / "Scripts" / "megazword.exe"
    return str(venv) if venv.is_file() else None


def reading() -> str:
    exe = find_megazword()
    if not exe:
        return "megazword is not on PATH here, so read the usage board in Q now."
    try:
        return run([exe, "startup"], 35)[:9500]
    except (OSError, subprocess.SubprocessError) as exc:
        return f"Startup reading unavailable ({type(exc).__name__}); do not retry or open a browser automatically."


def already_said(session: str, event: str) -> bool:
    """Project and user settings may both run this hook; say it once."""
    if not session:
        return False
    mark = Path.home() / ".megazword" / "hook_seen" / f"{session}-{event}"
    try:
        if mark.exists() and (event == "SessionStart" or time.time() - mark.stat().st_mtime < 5):
            return True
        mark.parent.mkdir(parents=True, exist_ok=True)
        mark.touch()
    except OSError:
        return False
    return False


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "prompt"
    try:
        session = json.loads(sys.stdin.read() or "{}").get("session_id", "")
    except (ValueError, OSError):
        session = ""
    event = "SessionStart" if mode == "start" else "UserPromptSubmit"
    if already_said(session, event):
        return
    if mode == "start":
        context = RULE + "\n\n" + reading()
    else:
        context = ("Reminder: if this message starts or assigns work, re-read live usage "
                   "(`megazword startup` once); reuse readings already in this turn. Do not repeat onboarding.")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # a broken hook must never block Phil's session
        pass
