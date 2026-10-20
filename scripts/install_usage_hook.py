"""One-time setup on Phil's PC for the usage-first rule. Run it yourself:

    python scripts/install_usage_hook.py          # shows what it would do
    python scripts/install_usage_hook.py --yes    # does it

1. Copies .claude/hooks/usage_check.py to ~/.claude/hooks/ and adds it to your
   personal Claude Code settings (~/.claude/settings.json), so Claude sessions in
   every folder see live usage before they start work. Existing settings are kept.
2. Windows: schedules "MegaZword-UsageBoard" every 15 minutes, which refreshes
   the usage board comment in Q (scripts/publish_usage.py; needs `gh` logged in,
   never calls a model).

Undo: remove the two usage_check.py entries from ~/.claude/settings.json and run
`schtasks /Delete /TN MegaZword-UsageBoard /F`.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / ".claude" / "hooks" / "usage_check.py"
TASK = "MegaZword-UsageBoard"


def add_user_hook(apply: bool) -> str:
    target = Path.home() / ".claude" / "hooks" / "usage_check.py"
    settings_path = Path.home() / ".claude" / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}
    hooks = settings.setdefault("hooks", {})
    missing = []
    for event, mode, timeout in (("SessionStart", "start", 90), ("UserPromptSubmit", "prompt", 10)):
        entries = hooks.setdefault(event, [])
        if not any("usage_check.py" in h.get("command", "")
                   for e in entries for h in e.get("hooks", [])):
            missing.append(event)
            entries.append({"hooks": [{"type": "command", "timeout": timeout,
                                       "command": f'python "{target}" {mode}'}]})
    if not apply:
        return f"would copy the hook to {target} and add {missing or 'nothing'} to {settings_path}"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HOOK, target)
    if missing:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = settings_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        tmp.replace(settings_path)
    return f"copied the hook to {target}; added {missing or 'nothing (already there)'}"


def schedule_board(apply: bool) -> str:
    if os.name != "nt":
        return "usage board task: Windows only, skipped"
    if subprocess.run(["schtasks", "/Query", "/TN", TASK], capture_output=True).returncode == 0:
        return f"{TASK} already scheduled"
    exe = shutil.which("megazword")
    folder = Path(exe).parent if exe else Path(sys.executable).parent
    py = next((p for p in (folder / "pythonw.exe", folder / "python.exe") if p.exists()),
              Path(sys.executable))
    cmd = f'"{py}" "{REPO / "scripts" / "publish_usage.py"}" --repo edotwedo/workshop --issue 33'
    if not apply:
        return f"would schedule {TASK} every 15 minutes: {cmd}"
    made = subprocess.run(["schtasks", "/Create", "/TN", TASK, "/SC", "MINUTE", "/MO", "15",
                           "/TR", cmd, "/F"], capture_output=True, text=True)
    if made.returncode != 0:
        return f"could not schedule {TASK}: {(made.stderr or made.stdout).strip()[:200]}"
    return f"scheduled {TASK} every 15 minutes"


def main() -> int:
    apply = "--yes" in sys.argv
    print(add_user_hook(apply))
    print(schedule_board(apply))
    if not apply:
        print("Nothing changed. Run again with --yes to do it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
