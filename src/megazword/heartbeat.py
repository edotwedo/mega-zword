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

GITEA = "http://127.0.0.1:3000/edotwedo/mega-zword.git"
TASK_NAME = "MegaZword-Heartbeat"
LOCK_HOURS = 3
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


def next_item(items: list[Item], status: str) -> tuple[Item | None, str]:
    for item in items:
        if item.mark in ("x", "phil"):
            continue
        if item.mark == "!":
            return None, f"#{item.num} {item.title} failed last time; waiting for a person"
        if claimed(item, status):
            return None, f"#{item.num} {item.title} is claimed by a seat; waiting (no skipping ahead)"
        return item, ""
    return None, "roadmap finished"


def home() -> Path:
    path = config.HOME / "heartbeat"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _locked() -> bool:
    """Take the beat lock atomically; True if another live beat holds it."""
    lock = home() / "lock"
    for _ in range(2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                age = datetime.now().timestamp() - lock.stat().st_mtime
            except FileNotFoundError:
                continue
            if age < LOCK_HOURS * 3600:
                return True
            lock.unlink(missing_ok=True)  # stale: a beat that died long ago
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(str(datetime.now()))
        return False
    return True


def _record(**row) -> None:
    row = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), **row}
    with (home() / "beats.jsonl").open("a", encoding="utf-8") as out:
        out.write(json.dumps(row) + "\n")


def _show(clone: Path, path: str) -> str:
    res = night.git(["show", f"origin/main:{path}"], clone)
    return res.stdout if res.returncode == 0 else ""


def merge(clone: Path, branch: str, backends, cfg, review_fn=None) -> str:
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
        if ahead.returncode != 0:
            return "not merged: main moved while the job ran; the next beat starts fresh"
        names = night.git(["diff", "--name-only", f"origin/main...origin/{branch}"], work).stdout.split()
        if names and all(n.startswith(LOG_ONLY) for n in names):
            return "not merged: only notes changed, no real progress"
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
        return f"merged into main ({len(raw)} reviewers, no agreed high findings)"
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
        item, why = next_item(parse(roadmap), status)
        if item is None:
            return _done(write, why)
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
        _record(item=item.num, status=out.status, ai=out.ai, branch=out.branch,
                tests=out.tests, result=result)
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
    p.add_argument("action", nargs="?", choices=("status", "run", "install", "remove"), default="status")
    p.add_argument("--start", default="09:00", help="first beat of the day (install)")
    p.add_argument("--until", default="23:00", help="last beat of the day (install)")
    p.add_argument("--every", type=int, default=2, help="hours between beats (install)")
    p.add_argument("--yes", action="store_true", help="really create the scheduled task")


def command(args, backends, cfg: config.Config) -> int:
    if args.action == "run":
        beat(backends, cfg)
        return 0
    if args.action == "install":
        return install(args.start, args.every, args.until, args.yes)
    if args.action == "remove":
        res = night._schtasks(["/Delete", "/TN", TASK_NAME, "/F"])
        print("[heartbeat] removed" if res.returncode == 0 else "[heartbeat] no task to remove")
        return 0
    return status()
