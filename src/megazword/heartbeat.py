"""Heartbeat: keep Mega Zword's roadmap moving without anyone asking.

Each beat (Phil, 2026-10-16: "an enforced roadmap"):
1. Stop if the STOP file is set, another beat is running, or no AI has room.
2. Read docs/ROADMAP.md and docs/STATUS.md from local Gitea main.
3. Take the first open item, in order. If a seat has claimed it ("ROADMAP #N" on
   an Active line of STATUS), wait: never skip ahead. `[phil]` items are skipped.
4. Hand one small, testable step of that item to Night Shift's job runner (own
   worktree, free models first, paid only above the usage floor, tests, secret
   check, pushed to a night/ branch).
5. Merge that branch into main only if its tests passed and free reviewers raise
   no high-severity finding that two of them agree on. Otherwise leave the branch
   for a person or seat to look at.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import config, night
from .filelock import write_atomic

GITEA = "http://127.0.0.1:3000/edotwedo/mega-zword.git"
TASK_NAME = "MegaZword-Heartbeat"
LOCK_HOURS = 3
MAX_FAILS = 2  # same step failing this many beats in a row on the same main: shelve it
SEAT = "heartbeat"  # its card in `megazword brief` / Catch me up
ITEM = re.compile(r"^(?P<num>\d+)\.\s*\[(?P<mark>[ ~x!]|phil)\]\s*\*\*(?P<title>[^*]+)\*\*(?P<rest>.*)$")
HANDOFF = re.compile(r"docs/handoffs/[\w.-]+\.md")

STEP = """ROADMAP item {num}: {title}

{body}
{handoff}
Do the NEXT small, testable step toward this item only: one focused change to source
code, tests or user docs that keeps the whole test suite passing. Writing plans, notes or
copies of this text is not a step. Read docs/STATUS.md, AGENTS.md and the files you change
first. Add tests for what you add. Then, in {log_file}, append one dated line under a
"## Heartbeat log" heading: what you did, and the exact next step. Do not create any other
handoff file."""

# A step that only touches these paths made no real progress and is not merged.
LOG_ONLY = ("docs/handoffs/", "docs/STATUS.md", "docs/ROADMAP.md")


@dataclass
class Item:
    num: int
    mark: str
    title: str
    body: str
    done_when: str


def parse(text: str) -> list[Item]:
    """Numbered items under "## Next, in order"; body = the item's lines."""
    section = text.split("## Next, in order", 1)[-1]
    items: list[Item] = []
    for line in section.splitlines():
        m = ITEM.match(line.strip())
        if m:
            items.append(Item(int(m["num"]), m["mark"], m["title"].strip(), line.strip(), ""))
        elif items and line.startswith((" ", "\t")) and line.strip():
            items[-1].body += "\n" + line.strip()
        elif line.startswith("## "):
            break
    for item in items:
        done = re.search(r"Done when:\s*(.+)", item.body)
        item.done_when = done.group(1).strip() if done else "one focused step is done and the tests pass"
    return items


def claimed(item: Item, status: str) -> bool:
    active = [l for l in status.splitlines()[:6] if re.match(r"\*\*(Also )?[Aa]ctive", l)]
    return any(re.search(rf"ROADMAP #{item.num}\b", l) for l in active)


def next_item(items: list[Item], status: str, shelved=()) -> tuple[Item | None, str]:
    """First item that isn't done, waiting on Phil, failed, shelved or claimed.

    Phil (2026-10-17): a stuck step is shelved with a note and the heartbeat
    picks another task; it never stops dead.
    """
    skipped = []
    for item in items:
        if item.mark in ("x", "phil"):
            continue
        if item.mark == "!" or item.num in shelved or claimed(item, status):
            skipped.append(f"#{item.num}")
            continue
        return item, ""
    if skipped:
        return None, f"nothing to pick: {', '.join(skipped)} shelved, failed or claimed"
    return None, "roadmap finished"


def home() -> Path:
    path = config.HOME / "heartbeat"
    path.mkdir(parents=True, exist_ok=True)
    return path


def shelf() -> dict:
    try:
        data = json.loads((home() / "shelf.json").read_text(encoding="utf-8"))
        return {int(k): v for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_shelf(data: dict) -> None:
    write_atomic(home() / "shelf.json", json.dumps({str(k): v for k, v in data.items()}, indent=2))


def notes_path() -> Path:
    return home() / "notes-for-phil.md"


def shelve(item: Item, base: str, tries: list[str]) -> None:
    """Set a stuck step aside and leave Phil a note for when he's back."""
    data = shelf()
    data[item.num] = {"title": item.title, "at": datetime.now().isoformat(timespec="minutes"),
                      "base": base[:12]}
    _save_shelf(data)
    lines = [f"\n## Shelved #{item.num} {item.title} ({data[item.num]['at']})",
             f"It failed {MAX_FAILS} beats in a row on main {base[:12]}, so the heartbeat moved on.",
             "What happened:", *(f"- {t}" for t in tries),
             f"To put it back: fix or clarify the step, then `megazword heartbeat unshelve {item.num}`.\n"]
    with notes_path().open("a", encoding="utf-8") as out:
        out.write("\n".join(lines))


def unshelve(num: int, write=print) -> int:
    data = shelf()
    if data.pop(num, None) is None:
        write(f"[heartbeat] #{num} is not on the shelf")
        return 1
    _save_shelf(data)
    write(f"[heartbeat] #{num} is back in the work order")
    return 0


def _card(state: str, doing: str, done: str, blocked: str = "", next_step: str = "") -> None:
    from . import briefing
    try:
        briefing.publish({"seat": SEAT, "project": "mega-zword", "state": state, "doing": doing,
                          "done": done, "blocked": blocked, "next": next_step})
    except (OSError, ValueError):
        pass  # the card is a convenience; never fail a beat over it


def _locked() -> bool:
    """Take the beat lock atomically; True if another live beat holds it."""
    lock = home() / "lock"
    for _ in range(2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                age = datetime.now().timestamp() - lock.stat().st_mtime
                pid = int((lock.read_text(encoding="utf-8").split() or ["0"])[0])
            except FileNotFoundError:
                continue
            except ValueError:
                pid = 0
            # A live beat keeps its lock however long it runs (seven AIs at 30 minutes
            # each can pass 3 hours); the age only matters when no PID was written.
            if _alive(pid) if pid else age < LOCK_HOURS * 3600:
                return True
            lock.unlink(missing_ok=True)  # stale: its beat died or is long gone
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(f"{os.getpid()} {datetime.now()}")
        return False
    return True


def _alive(pid: int) -> bool:
    """Is that process still running? Never signals it (os.kill would end it on Windows)."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _record(**row) -> None:
    row = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), **row}
    with (home() / "beats.jsonl").open("a", encoding="utf-8") as out:
        out.write(json.dumps(row) + "\n")


def _failures(num: int, base: str) -> int:
    """Beats in a row, newest first, where step #num failed on this same main.

    A fix pushed to main changes `base` and so clears the count. Beats that
    found no AI with room, or a broken baseline, cost no model use and don't count.
    """
    path = home() / "beats.jsonl"
    count = 0
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    for line in reversed(lines):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("item") != num or row.get("base") != base:
            break
        result = str(row.get("result", ""))
        if "merged into main" in result:
            break
        # No room, or a broken baseline (an environment problem, found before any
        # model call), says nothing about the step itself.
        if "no AI has room" not in result and "baseline tests failed" not in result:
            count += 1
    return count


def _tries(num: int, base: str) -> list[str]:
    path = home() / "beats.jsonl"
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("item") == num and row.get("base") == base:
            rows.append(f"{row.get('time', '')[:16]} {row.get('result', '')}"[:400])
    return rows[-MAX_FAILS:]


def _shelf_line(shelved: dict) -> str:
    if not shelved:
        return ""
    names = ", ".join(f"#{n} {v.get('title', '')}" for n, v in sorted(shelved.items()))
    return f"Shelved for Phil: {names}. Notes: {notes_path()}"


def _show(clone: Path, path: str) -> str:
    res = night.git(["show", f"origin/main:{path}"], clone)
    return res.stdout if res.returncode == 0 else ""


def _retest(work: Path) -> tuple[bool, str]:
    """Full tests on the rebased step, the same command Night Shift uses."""
    cmd, env = night.test_command(work, night.Job(0, " ", "", "rebased step", "tests pass"))
    if not cmd:
        return False, "no test command to check it"
    res = night.run_cmd(cmd, work, night.TEST_MINUTES * 60, env)
    tail = ((res.stdout or res.stderr or "").strip().splitlines() or [""])[-1]
    return res.returncode == 0, tail[:200]


def merge(clone: Path, branch: str, backends, cfg, review_fn=None, test_fn=None) -> str:
    """Review the night branch and merge it into main if nothing blocks it."""
    from . import review
    work = night.home() / "work" / ("merge_" + branch.replace("/", "_"))
    night.git(["worktree", "remove", "--force", str(work)], clone)
    night.git(["fetch", "--quiet", "origin"], clone)
    night._check(night.git(["worktree", "add", "--quiet", "--detach", str(work), f"origin/{branch}"], clone),
                 "git worktree add")
    try:
        # Only the exact commit Night Shift tested may reach main: it must sit
        # directly on today's main (fast-forward), or the combination is untested.
        ahead = night.git(["merge-base", "--is-ancestor", "origin/main", f"origin/{branch}"], work)
        rebased = ""
        if ahead.returncode != 0:
            # Other seats push to main while a beat runs. Put the step on top of the
            # new main and test that exact result again instead of throwing it away.
            if night.git(["rebase", "--quiet", "origin/main"], work).returncode != 0:
                night.git(["rebase", "--abort"], work)
                return "not merged: main moved and the step conflicts with it; the next beat starts fresh"
            ok, detail = (test_fn or _retest)(work)
            if not ok:
                return f"not merged: main moved; tests fail on the new main ({detail})"
            rebased = ", rebased onto the new main and retested"
        names = night.git(["diff", "--name-only", "origin/main...HEAD"], work).stdout.split()
        if names and all(n.startswith(LOG_ONLY) for n in names):
            return "not merged: only notes changed, no real progress"
        if any(n.startswith("src/") for n in names) and not any(n.startswith("tests/") for n in names):
            return "not merged: code changed without tests"
        diff, _ = review.change(work, "origin/main")
        if review.clip(diff)[1]:
            return "not merged: change too big to review in one pass; needs a person"
        # Two usable reviews, so one model's false alarm can't block a merge and
        # a provider outage can't let an unreviewed change through.
        merged, raw, _ = (review_fn or review.collect)(work, backends, cfg, base="origin/main", count=2)
        if merged is None or len(raw) < 2:
            return f"not merged: needs 2 completed reviews, got {len(raw)}"
        stops = review.blocking(merged)
        if stops:
            return "not merged: reviewers agree on " + "; ".join(
                f"{f.path}:{f.line} {f.text[:80]}" for f in stops[:3])
        problem = night.secret_problem(work, since="origin/main")
        if problem:
            return "not merged: " + problem
        night._check(night.git(["push", "--quiet", "origin", "HEAD:refs/heads/main"], work, 600), "git push main")
        return f"merged into main ({len(raw)} reviewers, no agreed high findings{rebased})"
    finally:
        night.git(["worktree", "remove", "--force", str(work)], clone)


def beat(backends, cfg: config.Config, runner=None, merger=merge, write=print) -> str:
    if night.stop_path().exists():
        return _done(write, "skipped: STOP file is set (`megazword night resume` clears it)")
    if _locked():
        return _done(write, "skipped: another beat is running")
    try:
        clone = night.cache_clone(GITEA)
        roadmap, status = _show(clone, "docs/ROADMAP.md"), _show(clone, "docs/STATUS.md")
        shelved = shelf()
        item, why = next_item(parse(roadmap), status, shelved)
        if item is None:
            _card("waiting", "", why, _shelf_line(shelved))
            return _done(write, why)
        base = night.git(["rev-parse", "origin/main"], clone).stdout.strip()
        refs = HANDOFF.findall(item.body)
        handoff = "".join(f"\nHandoff {ref}:\n{_show(clone, ref)}\n" for ref in refs[:1])
        log_file = refs[0] if refs else f"docs/handoffs/roadmap-{item.num}.md"
        task = STEP.format(num=item.num, title=item.title, body=item.body, handoff=handoff,
                           log_file=log_file)
        job = night.Job(0, " ", GITEA, task, item.done_when)
        shift = runner or night.Night(backends, log=lambda s: write(f"[heartbeat] {s}"), cfg=cfg)
        out = shift.run_job(job)
        result = f"#{item.num} {item.title}: {out.status}"
        if out.reason:
            result += f" ({out.reason[:200]})"
        if out.status == "done" and out.tests == "passed" and out.branch:
            result += "; " + merger(clone, out.branch, backends, cfg)
        _record(item=item.num, base=base, status=out.status, ai=out.ai, branch=out.branch,
                tests=out.tests, result=result)
        merged = "merged into main" in result
        if not merged and _failures(item.num, base) >= MAX_FAILS:
            shelve(item, base, _tries(item.num, base))
            shelved = shelf()
            result += f"; shelved #{item.num}, note in {notes_path()}"
        _card("blocked" if shelved else "working", f"roadmap #{item.num} {item.title}",
              result[:600], _shelf_line(shelved), "next beat picks the next open step")
        return _done(write, result)
    finally:
        (home() / "lock").unlink(missing_ok=True)


def _done(write, text: str) -> str:
    write(f"[heartbeat] {text}")
    return text


def task_command() -> str:
    from .desktop import launcher_python
    return f'"{launcher_python()}" -m megazword.cli heartbeat run'


def install(start: str, every_hours: int, until: str, yes: bool = False) -> int:
    """Windowless repeating task: every N hours from `start` to `until` each day."""
    for t in (start, until):
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t):
            print(f"[heartbeat] times look like 09:00, not '{t}'", file=sys.stderr)
            return 2
    h1, m1 = map(int, start.split(":"))
    h2, m2 = map(int, until.split(":"))
    minutes = (h2 * 60 + m2) - (h1 * 60 + m1)
    if minutes <= 0 or every_hours < 1:
        print("[heartbeat] --until must be after --start, and --every at least 1 hour", file=sys.stderr)
        return 2
    duration = f"{minutes // 60:02d}:{minutes % 60:02d}"
    cmd = task_command()
    print(f"[heartbeat] task {TASK_NAME}: every {every_hours}h from {start} to {until}: {cmd}")
    if not yes:
        print("[heartbeat] add --yes to create it")
        return 0
    res = night._schtasks(["/Create", "/TN", TASK_NAME, "/SC", "DAILY", "/ST", start,
                           "/RI", str(every_hours * 60), "/DU", duration, "/TR", cmd, "/F"])
    if res.returncode != 0:
        print(f"[heartbeat] schtasks failed: {(res.stderr or res.stdout).strip()[:300]}", file=sys.stderr)
        return 1
    print(f"[heartbeat] scheduled. Pause: `megazword night stop`. Remove: `megazword heartbeat remove`.")
    return 0


def status(write=print) -> int:
    path = home() / "beats.jsonl"
    rows = path.read_text(encoding="utf-8").splitlines()[-5:] if path.exists() else []
    write(f"STOP file: {'set' if night.stop_path().exists() else 'not set'}")
    shelved = shelf()
    for num, row in sorted(shelved.items()):
        write(f"shelved: #{num} {row.get('title', '')} since {row.get('at', '')}")
    if shelved:
        write(f"notes for Phil: {notes_path()}")
    if log_path().exists():
        write(f"beat log: {log_path()}")
    write("last beats:" if rows else "no beats yet")
    for line in rows:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        write(f"  {row.get('time', '')[:16]}  {row.get('result', '')}")
    return 0


def add_parser(sub) -> None:
    p = sub.add_parser("heartbeat", help="work the roadmap on a schedule")
    p.add_argument("action", nargs="?", choices=("status", "run", "install", "remove", "unshelve"),
                   default="status")
    p.add_argument("item", nargs="?", type=int, help="roadmap item number (unshelve)")
    p.add_argument("--start", default="09:00", help="first beat of the day (install)")
    p.add_argument("--until", default="23:00", help="last beat of the day (install)")
    p.add_argument("--every", type=int, default=2, help="hours between beats (install)")
    p.add_argument("--yes", action="store_true", help="really create the scheduled task")


def log_path() -> Path:
    return home() / "beat.log"


def logged(text: str) -> None:
    """Print and keep: the scheduled task runs windowless, so nothing sees stdout."""
    print(text)
    try:
        home().mkdir(parents=True, exist_ok=True)
        with log_path().open("a", encoding="utf-8") as out:
            out.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {text}\n")
    except OSError:
        pass  # the log is bookkeeping; never fail a beat over it


def command(args, backends, cfg: config.Config) -> int:
    if args.action == "run":
        beat(backends, cfg, write=logged)
        return 0
    if args.action == "install":
        return install(args.start, args.every, args.until, args.yes)
    if args.action == "unshelve":
        if args.item is None:
            print("[heartbeat] unshelve needs a roadmap item number, e.g. `megazword heartbeat unshelve 4`")
            return 2
        return unshelve(args.item)
    if args.action == "remove":
        res = night._schtasks(["/Delete", "/TN", TASK_NAME, "/F"])
        print("[heartbeat] removed" if res.returncode == 0 else "[heartbeat] no task to remove")
        return 0
    return status()
