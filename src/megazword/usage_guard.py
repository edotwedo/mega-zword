"""Usage guard: keep a plan from running dry before it renews.

`spot` warns when a window is already at its reserve. The guard looks one step earlier - at
the *burn rate*. If a plan is ahead of its own clock (used% above elapsed%), it projects the
day the window runs dry; when that lands before the reset the plan is marked `throttle`.
Routing already prefers roomier plans, so a throttled plan quietly stops being handed work
and its budget stretches to the renewal instead of dying two weeks early.

One scheduled tick, `megazword guard install`, runs `guard run --post`: it reloads the live
meters, writes `~/.megazword/guard.json`, and posts a single room line only when the state
changes. No model call while idle; `megazword guard stop` halts it. The guard keeps its own
STOP file, deliberately not night's: night's `STOP` is a long-lived switch that is often set
for unrelated reasons, and a monitor must not go quiet because some other loop was parked.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import config

TASK_NAME = "MegaZword-Guard"
DEFAULT_EVERY = 30  # minutes between checks


def home() -> Path:
    return config.HOME


def state_path() -> Path:
    return home() / "guard.json"


def stop_path() -> Path:
    return home() / "guard" / "STOP"


def evaluate(home_dir: Path | None = None, now: datetime | None = None) -> dict:
    """Read the live meters; for each plan give its verdict, pace and projected dry-out."""
    from .pacing import project, status, window_length
    from .usage_sources import all_usage

    now = now or datetime.now(timezone.utc)
    plans: list[dict] = []
    for usage in all_usage((home_dir or home()) / "log.jsonl"):
        result = status(usage, now)
        gaps, used = {}, {}
        for window in usage.windows:
            if not window_length(window.name)[1]:
                continue
            days = project(window, now)
            if days is not None:
                gaps[window.name] = round(days, 1)
                used[window.name] = round(float(window.used_percent), 1)
        # The window the gap belongs to. gap_windows is sorted by name, so its first entry is
        # "5-hour" whenever that window has any gap - which once labelled a weekly 7-day gap as
        # "~7d before its 5-hour reset", an impossible line.
        worst = max(gaps, key=gaps.get) if gaps else None
        plans.append({
            "service": usage.service,
            "verdict": result.verdict,
            "worst_pace": round(result.worst_pace, 1),
            "max_used_percent": round(result.max_used_percent, 1),
            "gap_days": max(gaps.values(), default=0.0),
            "gap_windows": sorted(name for name, days in gaps.items() if days > 0),
            "gap_window": worst if worst and gaps[worst] > 0 else None,
            "gap_used_percent": used.get(worst) if worst else None,
        })
    # Worst first: plans that will run dry before they renew, then the biggest gap.
    plans.sort(key=lambda plan: (plan["gap_days"] <= 0, -plan["gap_days"], plan["service"]))
    throttled = [plan["service"] for plan in plans if plan["verdict"] == "throttle"]
    return {
        "as_of": now.isoformat(timespec="seconds"),
        "plans": plans,
        "throttled": throttled,
        "suggested_bias": "free-first" if throttled else "as-configured",
    }


def _line(state: dict) -> str:
    """One room line, or '' when nothing is wrong.

    A plan at its floor is the loudest thing this can say, so it goes first and says OUT - a
    spent plan with a gap used to be reported only as "over pace - dry in ~Nd", which is how
    Gemini's weekly limit was missed on 2026-10-23. A gap is a warning, not a spent plan, and
    is worded as the gap it is: days before its own reset that the window would run dry.
    """
    spent, gaps = [], []
    for plan in state.get("plans", []):
        if plan["verdict"] == "out":
            spent.append(f"{plan['service']} OUT ({plan['max_used_percent']:.0f}% used)")
        elif round(plan["gap_days"]) >= 1:
            # Under half a day rounds to "~0d", which reads as "empty now" and is not worth a post.
            window = (plan.get("gap_window")
                      or (plan["gap_windows"][0] if plan["gap_windows"] else "monthly"))
            used = plan.get("gap_used_percent")
            # Say how much is used: "would run dry" alone was read as "nearly empty" when the
            # plan was at 30% (2026-10-25).
            shown = f"{plan['service']} {window} {used:.0f}% used" if used is not None \
                else plan["service"]
            # Whole days on purpose: the projection drifts a few tenths on every run, and a
            # line that changed every 30 minutes would be noise, not a state change.
            gaps.append(f"{shown}, would run dry ~{round(plan['gap_days'])}d before "
                        f"its {window} reset")
    if not spent and not gaps:
        return ""
    parts = []
    if spent:
        parts.append("STOP - " + ", ".join(spent))
    if gaps:
        parts.append("over pace: " + "; ".join(gaps))
    return "guard: " + " | ".join(parts)


def run(post: bool = False, home_dir: Path | None = None, now: datetime | None = None,
        write: Callable[[str], None] = print) -> int:
    if stop_path().exists():
        write("[guard] STOP file is there; not running")
        return 0
    try:
        state = evaluate(home_dir, now)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        write(f"[guard] usage unavailable: {exc}")
        return 2
    path = state_path()
    previous = None
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    for plan in state["plans"]:
        write(f"  {plan['service']:8} {plan['verdict']:9} pace {plan['worst_pace']:+5.1f} "
              f"max {plan['max_used_percent']:3.0f}%  gap ~{plan['gap_days']:g}d")
    line = _line(state)
    if not line:
        write("[guard] every plan is within its own pace")
        return 0
    write(line)
    if post and (previous is None or _line(previous) != line):
        _say(line, write)
        _push(line, write)
    return 0


def _say(line: str, write: Callable[[str], None]) -> None:
    from . import room
    # Never post under a seat's name. The scheduled task has no MEGAZWORD_SEAT, and a guard line
    # signed "cinder-21" reads as the conductor talking (Harbor022, 2026-10-23).
    seat = os.environ.get("MEGAZWORD_SEAT") or "guard"
    try:
        room.say("hive", line, author=seat, cfg=config.load())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        write(f"[guard] room post failed: {exc}")


def _push(line: str, write: Callable[[str], None]) -> None:
    """Buzz the phone as well as the room.

    A room line is passive: Phil has to remember to look, and on 2026-10-23 he did not, so a
    plan hit its weekly limit unannounced. `announce.ping` is an ntfy push plus a Windows
    toast, so a guard post actually reaches him. Best-effort; it never fails the tick.
    """
    from . import announce
    try:
        announce.ping(line, config.load())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        write(f"[guard] alert failed: {exc}")


def status(write: Callable[[str], None] = print) -> int:
    path = state_path()
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        write("[guard] no reading yet; run `megazword guard run`")
        return 1
    write(f"guard reading {state.get('as_of', '?')} ({path})")
    for plan in state.get("plans", []):
        write(f"  {plan['service']:8} {plan['verdict']:9} pace {plan['worst_pace']:+5.1f} "
              f"max {plan['max_used_percent']:3.0f}%  gap ~{plan['gap_days']:g}d")
    line = _line(state)
    write(line or "[guard] every plan is within its own pace")
    return 0


def task_command() -> str:
    from .desktop import launcher_python
    return f'"{launcher_python()}" -m megazword.cli guard run --post'


def install(every: int = DEFAULT_EVERY, yes: bool = False,
            write: Callable[[str], None] = print) -> int:
    """Every `every` minutes, windowless (pythonw). Prints the plan; `--yes` creates it."""
    from . import night
    if every < 1:
        write("[guard] --every wants a positive number of minutes")
        return 2
    command = task_command()
    write(f"[guard] task {TASK_NAME}: every {every} min: {command}")
    write("[guard] it runs as you, only while you're signed in (the PC can be locked).")
    if not yes:
        write("[guard] add --yes to create it")
        return 0
    result = night._schtasks(["/Create", "/TN", TASK_NAME, "/SC", "MINUTE", "/MO", str(every),
                              "/TR", command, "/F"])
    if result.returncode != 0:
        write(f"[guard] schtasks failed: {(result.stderr or result.stdout).strip()[:300]}")
        return 1
    write(f"[guard] scheduled {TASK_NAME} every {every} min. Off: `megazword guard stop` "
          "(skips runs) or `megazword guard remove` (deletes the task)")
    return 0


def remove(write: Callable[[str], None] = print) -> int:
    from . import night
    result = night._schtasks(["/Delete", "/TN", TASK_NAME, "/F"])
    if result.returncode != 0:
        write(f"[guard] schtasks: {(result.stderr or result.stdout).strip()[:300]}")
        return 1
    write(f"[guard] removed {TASK_NAME}")
    return 0


def command(args, cfg=None, write: Callable[[str], None] = print) -> int:
    action = getattr(args, "guard_cmd", "status")
    if action == "run":
        return run(post=getattr(args, "post", False), write=write)
    if action == "status":
        return status(write=write)
    if action == "install":
        return install(every=getattr(args, "every", DEFAULT_EVERY),
                       yes=getattr(args, "yes", False), write=write)
    if action == "remove":
        return remove(write=write)
    if action == "stop":
        stop_path().parent.mkdir(parents=True, exist_ok=True)
        stop_path().write_text("stop\n", encoding="utf-8")
        write("[guard] STOP file written; runs are off (`megazword guard resume` undoes it)")
        return 0
    if action == "resume":
        stop_path().unlink(missing_ok=True)
        write("[guard] STOP file removed; runs are back on")
        return 0
    write(f"[guard] unknown action: {action}")
    return 2


def add_parser(sub) -> None:
    guard = sub.add_parser("guard", help="keep a plan from running dry before it renews")
    gsub = guard.add_subparsers(dest="guard_cmd", metavar="ACTION")
    gsub.required = True
    run_parser = gsub.add_parser("run", help="read the live meters and write guard.json")
    run_parser.add_argument("--post", action="store_true",
                            help="post one room line when the state changes")
    gsub.add_parser("status", help="show the last guard reading")
    inst = gsub.add_parser("install", help="scheduled task that checks the pace (windowless)")
    inst.add_argument("--every", type=int, default=DEFAULT_EVERY,
                      help=f"minutes between checks (default {DEFAULT_EVERY})")
    inst.add_argument("--yes", action="store_true", help="really create it")
    gsub.add_parser("remove", help="delete the scheduled task")
    gsub.add_parser("stop", help="skip runs (writes the guard's own STOP file)")
    gsub.add_parser("resume", help="remove the STOP file")
