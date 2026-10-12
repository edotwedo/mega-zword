"""Usage-first hook (Phil's rule): before any work, check every AI's usage and
write a labor plan. Run by Claude Code at session start ("start") and on every
prompt ("prompt"). Prints hook JSON; never fails the session."""

import json
import shutil
import subprocess
import sys

BOARD = "https://github.com/edotwedo/workshop/pull/33#issuecomment-6115098816"
RULE = ("USAGE FIRST (Phil's standing rule): before starting, claiming or handing out any work, "
        "check every AI's usage and write a labor plan (which AI does which part, by spare usage "
        "and fit), quoting the reading. On Phil's PC run `megazword usage`. Elsewhere read the "
        f"usage board in Q ({BOARD}, comment 6115098816 on edotwedo/workshop PR #33); if it is "
        "over 30 minutes old, say the PC is asleep. Do this before work, every time.")


def reading() -> str:
    exe = shutil.which("megazword")
    if not exe:
        return "megazword is not on PATH here, so read the usage board in Q now."
    try:
        out = subprocess.run([exe, "usage"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=45)
        text = (out.stdout or out.stderr).strip()
        return "Current `megazword usage`:\n" + text[:3000] if text else "megazword usage printed nothing."
    except (OSError, subprocess.SubprocessError) as exc:
        return f"megazword usage failed ({type(exc).__name__}); read the usage board in Q."


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "prompt"
    if mode == "start":
        event, context = "SessionStart", RULE + "\n\n" + reading()
    else:
        event, context = "UserPromptSubmit", (
            "Reminder: if this message starts or assigns work, check usage and write the labor "
            "plan first (rule in your session-start context; board: " + BOARD + ").")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # a broken hook must never block Phil's session
        pass
