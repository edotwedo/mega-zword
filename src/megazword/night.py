"""Night Shift: work through docs/QUEUE.md while Phil sleeps (`megazword night`).

Each job gets a fresh checkout of its repo, an AI with spare usage edits files
there, then this module (never the AI) runs the tests, commits and pushes the
branch `night/<date>-<n>`. The AI never touches git, so a sandboxed CLI only
has to write files in its folder. Nothing is ever pushed to main.

Stop rules: a per-job time cap, a usage floor (an AI with less than 15% left,
or no fresh meter reading, is skipped), a STOP file (`megazword night stop`),
and a cap on jobs per night. At the end one summary with no @-tags can go to Q.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import config
from .backends import Backend, _kill_tree, process_group

QUEUE_REPO = "edotwedo/mega-zword"
QUEUE_FILE = "docs/QUEUE.md"
TASK_NAME = "MegaZword-NightShift"
FLOOR = 15          # percent left; below this an AI gets no night work
JOB_MINUTES = 30    # AI time cap per job
TEST_MINUTES = 20   # test run cap per job
MAX_JOBS = 5
LOCK_STALE_HOURS = 12

LINE = re.compile(r"^\s*-\s*\[(?P<mark>[ xX!])\]\s*(?P<body>.+?)\s*$")
SECRET = re.compile(r"(sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}"
                    r"|xai-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY)")
SECRET_FILES = re.compile(r"(^|/)(\.env(\..*)?|.*\.pem|.*\.key|\.credentials\.json)$")

PROMPT = """You are working unattended overnight, in the repository in the current folder ({repo}).
Task: {task}
Done when: {done}
Rules: edit files in this folder only. Do not run git, commit or push; Mega Zword does that
after you finish and runs the tests. Never add secrets, keys or logins. Keep the change small
and focused on the task. When finished, reply with one or two lines saying what you changed."""


def home() -> Path:
    return config.HOME / "night"


def stop_path() -> Path:
    return home() / "STOP"


@dataclass
class Job:
    line_no: int          # 0-based line in QUEUE.md
    mark: str             # " " todo, "x" done, "!" failed
    repo: str
    task: str
    done_when: str
    test: str = ""        # optional test command; "" = detect

    @property
    def key(self) -> str:
        return hashlib.sha1(f"{self.repo}|{self.task}".encode()).hexdigest()[:12]


@dataclass
class Outcome:
    job: Job
    status: str           # "done" | "failed" | "skipped"
    reason: str = ""
    branch: str = ""
    ai: str = ""
    tests: str = ""       # "passed" | "failed" | "none" | ""
    tried: list[str] = field(default_factory=list)


def parse_queue(text: str) -> list[Job]:
    """One job per line: `- [ ] repo | task | done when: ... [| test: cmd]`.
    Lines that don't match (headings, notes) are ignored."""
    jobs = []
    for i, raw in enumerate(text.splitlines()):
        m = LINE.match(raw)
        if not m:
            continue
        parts = [p.strip() for p in m.group("body").split(" | ")]
        if len(parts) < 3 or not parts[0] or not parts[1]:
            continue
        done = re.sub(r"^done when:\s*", "", parts[2], flags=re.I)
        test = ""
        for extra in parts[3:]:
            if extra.lower().startswith("test:"):
                test = extra[5:].strip()
        jobs.append(Job(i, m.group("mark").lower(), parts[0], parts[1], done, test))
    return jobs


def mark_queue(text: str, outcomes: list[Outcome]) -> str:
    """QUEUE.md with each finished job's box ticked ([x] done, [!] failed) and its branch noted."""
    lines = text.splitlines(keepends=True)
    for o in outcomes:
        if o.status not in ("done", "failed"):
            continue
        i = o.job.line_no
        if i >= len(lines):
            continue
        end = "\n" if lines[i].endswith("\n") else ""
        line = lines[i].rstrip("\r\n")
        box = "[x]" if o.status == "done" else "[!]"
        line = re.sub(r"\[[ xX!]\]", box, line, count=1)
        note = o.branch or o.reason
        lines[i] = f"{line} <!-- {o.status} {datetime.now():%Y-%m-%d}: {note} -->{end}"
    return "".join(lines)


# ---------- processes (all windowless: the task runs under pythonw) ----------

def run_cmd(cmd: list[str], cwd: Path | None = None, timeout: float = 300,
            env: dict | None = None) -> subprocess.CompletedProcess:
    """Run a short command with no console window and no stdin; kill the whole
    tree on timeout. Never raises for a non-zero exit; check returncode."""
    exe = shutil.which(cmd[0]) or cmd[0]
    proc = subprocess.Popen([exe, *cmd[1:]], cwd=str(cwd) if cwd else None,
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8",
                            errors="replace", env=env, **process_group())
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        return subprocess.CompletedProcess(cmd, 124, "", f"timed out after {timeout:.0f}s")
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


def git(args: list[str], cwd: Path, timeout: float = 300) -> subprocess.CompletedProcess:
    return run_cmd(["git", *args], cwd, timeout)


def _check(res: subprocess.CompletedProcess, what: str) -> str:
    if res.returncode != 0:
        raise RuntimeError(f"{what} failed: {(res.stderr or res.stdout).strip()[-500:]}")
    return res.stdout


def _gh_path() -> str | None:
    """The real GitHub CLI; tests replace this so they can never post to Q."""
    return shutil.which("gh")


def _schtasks(args: list[str]) -> subprocess.CompletedProcess:
    """Windows Task Scheduler; tests replace this so they never register a task."""
    return run_cmd(["schtasks", *args], timeout=60)


# ---------- repos and branches ----------

def remote_url(repo: str) -> str:
    """`owner/name` means GitHub; anything else (a URL or a folder) is used as is."""
    if re.fullmatch(r"[\w.-]+/[\w.-]+", repo) and not Path(repo).exists():
        return f"https://github.com/{repo}.git"
    return repo


def cache_clone(repo: str) -> Path:
    """A clone kept under ~/.megazword/night/repos, fetched fresh each time.
    Phil's own working folders are never used: they can hold unpushed work."""
    url = remote_url(repo)
    # Short folder name (last part + hash): git on Windows fails on long paths.
    tail = re.sub(r"[^\w.-]+", "_", re.split(r"[/\\]", repo.strip("/\\"))[-1])[-30:]
    folder = home() / "repos" / f"{tail}-{hashlib.sha1(url.encode()).hexdigest()[:8]}"
    if not (folder / ".git").exists():
        folder.parent.mkdir(parents=True, exist_ok=True)
        _check(run_cmd(["git", "clone", "--quiet", url, str(folder)], timeout=600), "git clone")
    _check(git(["fetch", "--quiet", "--prune", "origin"], folder), "git fetch")
    return folder


def default_branch(clone: Path) -> str:
    res = git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], clone)
    name = res.stdout.strip() if res.returncode == 0 else ""
    return name or "origin/main"


def next_branch(clone: Path, date: str, taken: set[str]) -> str:
    """night/<date>-<n> with n one past anything already on the remote or used tonight."""
    res = git(["ls-remote", "--heads", "origin", f"night/{date}-*"], clone)
    used = set(taken)
    for line in res.stdout.splitlines():
        used.add(line.split("refs/heads/", 1)[-1].strip())
    n = 1
    while f"night/{date}-{n}" in used:
        n += 1
    return f"night/{date}-{n}"


def push_branch(work: Path, branch: str) -> str:
    """Push HEAD to a night/ branch only, then confirm the remote has that exact commit."""
    if not branch.startswith("night/") or branch in ("night/", "night/main"):
        raise RuntimeError(f"refusing to push '{branch}': night jobs only push night/ branches")
    sha = _check(git(["rev-parse", "HEAD"], work), "git rev-parse").strip()
    _check(git(["push", "--quiet", "origin", f"HEAD:refs/heads/{branch}"], work, 600), "git push")
    seen = _check(git(["ls-remote", "origin", f"refs/heads/{branch}"], work), "git ls-remote")
    if not seen.startswith(sha):
        raise RuntimeError(f"push of {branch} did not land (remote has {seen.strip()[:12] or 'nothing'})")
    return sha


def secret_problem(work: Path) -> str:
    """Why this change must not be committed, or "" if it looks clean."""
    names = _check(git(["diff", "--cached", "--name-only"], work), "git diff").splitlines()
    for name in names:
        if SECRET_FILES.search(name.replace("\\", "/")):
            return f"refused to commit {name} (looks like a secrets file)"
    diff = _check(git(["diff", "--cached", "-U0"], work), "git diff")
    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++") and SECRET.search(line):
            return "refused to commit: the change contains something that looks like a key"
    return ""


def test_command(work: Path, job: Job) -> tuple[list[str] | None, dict | None]:
    """The job's own test command, else pytest for a Python repo. The checkout's
    src/ goes first on PYTHONPATH so tests import this branch, not Phil's install."""
    env = dict(os.environ)
    if (work / "src").is_dir():
        env["PYTHONPATH"] = os.pathsep.join([str(work / "src"), env.get("PYTHONPATH", "")]).strip(os.pathsep)
    if job.test:
        if os.name == "nt":
            return ["cmd", "/c", job.test], env
        return ["sh", "-c", job.test], env
    if (work / "pyproject.toml").exists() and (work / "tests").is_dir():
        return [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], env
    return None, None


# ---------- choosing an AI ----------

def eligible(backends: dict[str, Backend], summaries: list, floor: int = FLOOR) -> tuple[list[str], list[str]]:
    """AIs that may take a night job, most room first, plus why the others can't.
    Fail closed: an unattended run has nobody to notice overspend, so an AI with no
    meter, an old reading, or less than `floor`% left is skipped."""
    from .meters import labor_order
    by_name = {s.service: s for s in summaries}
    ok, why = [], []
    for name, _reason in labor_order(summaries):
        if name not in backends:
            continue
        s = by_name[name]
        if s.state != "meter":
            why.append(f"{name}: {'out' if s.state == 'out' else 'no meter'}")
        elif s.stale:
            why.append(f"{name}: old meter reading")
        elif 100 - (s.used or 0) < floor:
            why.append(f"{name}: {100 - (s.used or 0):.0f}% left, under the {floor}% floor")
        elif not backends[name].available():
            why.append(f"{name}: not installed")
        else:
            ok.append(name)
    for name in backends:
        if name not in by_name:
            why.append(f"{name}: no meter")
    return ok, why


def live_summaries() -> list:
    from .meters import summarize_all
    from .usage_sources import all_usage
    try:
        out_until = config.load().out_until
    except (ValueError, TypeError, OSError):
        out_until = {}
    return summarize_all(all_usage(config.HOME / "log.jsonl"), out_until)


def usage_line(summaries: list) -> str:
    parts = []
    for s in summaries:
        if s.state == "meter":
            parts.append(f"{s.service} {s.used:.0f}% {s.window}")
        elif s.state == "out":
            parts.append(f"{s.service} out")
    return "; ".join(parts) or "no meters"


# ---------- one job ----------

class Night:
    def __init__(self, backends: dict[str, Backend], usage: Callable[[], list] = live_summaries,
                 log: Callable[[str], None] | None = None, floor: int = FLOOR,
                 job_minutes: float = JOB_MINUTES, test_minutes: float = TEST_MINUTES,
                 date: str | None = None):
        self.backends = backends
        self.usage = usage
        self.floor = floor
        self.job_seconds = job_minutes * 60
        self.test_seconds = test_minutes * 60
        self.date = date or f"{datetime.now():%Y-%m-%d}"
        self.taken: set[str] = set()
        self.log = log or (lambda s: None)

    def run_job(self, job: Job) -> Outcome:
        out = Outcome(job, "failed")
        summaries = self.usage()  # usage before every job (Phil's rule)
        names, why = eligible(self.backends, summaries, self.floor)
        self.log(f"usage: {usage_line(summaries)}")
        if not names:
            out.status, out.reason = "skipped", "no AI has room: " + "; ".join(why)
            return out
        try:
            clone = cache_clone(job.repo)
        except RuntimeError as exc:
            out.reason = str(exc)
            return out
        base = default_branch(clone)
        branch = next_branch(clone, self.date, self.taken)
        work = home() / "work" / branch.replace("/", "_")
        if work.exists():
            git(["worktree", "remove", "--force", str(work)], clone)
            shutil.rmtree(work, ignore_errors=True)
        git(["worktree", "prune"], clone)
        try:
            _check(git(["worktree", "add", "--quiet", "--detach", str(work), base], clone), "git worktree add")
            return self._work(job, out, names, work, branch)
        finally:
            git(["worktree", "remove", "--force", str(work)], clone)
            shutil.rmtree(work, ignore_errors=True)

    def _work(self, job: Job, out: Outcome, names: list[str], work: Path, branch: str) -> Outcome:
        prompt = PROMPT.format(repo=job.repo, task=job.task, done=job.done_when)
        for name in names:
            out.tried.append(name)
            backend = replace(self.backends[name], cwd=str(work), timeout=int(self.job_seconds))
            self.log(f"{branch}: {name} working on: {job.task}")
            result = backend.run(prompt)
            git(["add", "-A"], work)
            changed = git(["diff", "--cached", "--quiet"], work).returncode != 0
            if changed:
                out.ai = name
                break
            reason = result.error or "made no changes"
            self.log(f"{branch}: {name} {reason[:200]}")
            out.reason = f"{name}: {reason[:200]}"
            git(["reset", "--hard", "--quiet"], work)
            git(["clean", "-fdq"], work)
        else:
            return out
        problem = secret_problem(work)
        if problem:
            out.reason = problem
            return out
        # Commit the AI's change before the tests, so files the tests write stay out of it.
        msg = f"night: {job.task[:60]}\n\nNight Shift job by {out.ai}. Done when: {job.done_when}"
        _check(git(["-c", "core.hooksPath=", "commit", "--quiet", "-m", msg], work), "git commit")
        cmd, env = test_command(work, job)
        if cmd is None:
            out.tests = "none"
        else:
            res = run_cmd(cmd, work, self.test_seconds, env)
            out.tests = "passed" if res.returncode == 0 else "failed"
            tail = (res.stdout or res.stderr).strip().splitlines()[-1:] or [""]
            self.log(f"{branch}: tests {out.tests}: {tail[0][:200]}")
            if out.tests == "failed":
                out.reason = f"tests failed: {tail[0][:200]}"
        _check(git(["-c", "core.hooksPath=", "commit", "--quiet", "--amend", "-m",
                    f"{msg}\nTests: {out.tests}"], work), "git commit --amend")
        try:
            push_branch(work, branch)
        except RuntimeError as exc:
            out.reason = str(exc)
            return out
        self.taken.add(branch)
        out.branch = branch
        if out.tests != "failed":
            out.status, out.reason = "done", ""
        return out


# ---------- the whole night ----------

def summary_text(outcomes: list[Outcome], start_usage: str, end_usage: str, stopped: str) -> str:
    from .room import quiet_mentions
    lines = [f"Night Shift summary, {datetime.now():%Y-%m-%d %H:%M}",
             f"Usage at start: {start_usage}", f"Usage at end: {end_usage}", ""]
    if not outcomes:
        lines.append("No jobs ran.")
    for o in outcomes:
        tests = f", tests {o.tests}" if o.tests else ""
        where = f" on `{o.branch}`" if o.branch else ""
        by = f" by {o.ai}" if o.ai else ""
        reason = f" ({o.reason})" if o.reason else ""
        lines.append(f"- {o.status}{by}{where}{tests}: {o.job.task}{reason}")
    if stopped:
        lines += ["", f"Stopped early: {stopped}"]
    return quiet_mentions("\n".join(lines)).replace("@", "")


def post_to_q(text: str) -> bool:
    gh = _gh_path()
    if not gh:
        return False
    res = run_cmd([gh, "pr", "comment", "33", "--repo", "edotwedo/workshop", "--body", text], timeout=60)
    return res.returncode == 0


class Lock:
    """One night run at a time. A lock older than LOCK_STALE_HOURS is from a crashed run."""

    def __init__(self, path: Path):
        self.path = path
        self.held = False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if self.path.exists():
                age = datetime.now().timestamp() - self.path.stat().st_mtime
                if age > LOCK_STALE_HOURS * 3600:
                    self.path.unlink()
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            self.held = True
        except FileExistsError:
            pass
        return self

    def __exit__(self, *exc):
        if self.held:
            self.path.unlink(missing_ok=True)


def read_queue(queue: str | None) -> tuple[str, Path | None, str]:
    """Queue text, the clone it came from (None for a local file), and its repo."""
    if queue and Path(queue).is_file():
        return Path(queue).read_text(encoding="utf-8"), None, ""
    repo = queue or QUEUE_REPO
    clone = cache_clone(repo)
    base = default_branch(clone)
    res = git(["show", f"{base}:{QUEUE_FILE}"], clone)
    return (res.stdout if res.returncode == 0 else ""), clone, repo


def load_state() -> dict:
    try:
        return json.loads((home() / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    home().mkdir(parents=True, exist_ok=True)
    (home() / "state.json").write_text(json.dumps(state, indent=1), encoding="utf-8")


def push_queue_marks(clone: Path, text: str, outcomes: list[Outcome], night: Night) -> str:
    """Tick the finished jobs in QUEUE.md on its own night/ branch, for Phil or the lead to merge."""
    marked = mark_queue(text, outcomes)
    if marked == text:
        return ""
    branch = next_branch(clone, night.date, night.taken)
    work = home() / "work" / branch.replace("/", "_")
    shutil.rmtree(work, ignore_errors=True)
    git(["worktree", "prune"], clone)
    try:
        _check(git(["worktree", "add", "--quiet", "--detach", str(work), default_branch(clone)], clone),
               "git worktree add")
        (work / QUEUE_FILE).write_text(marked, encoding="utf-8", newline="")
        git(["add", QUEUE_FILE], work)
        _check(git(["-c", "core.hooksPath=", "commit", "--quiet", "-m", "night: mark queue"], work),
               "git commit")
        push_branch(work, branch)
        night.taken.add(branch)
        return branch
    finally:
        git(["worktree", "remove", "--force", str(work)], clone)
        shutil.rmtree(work, ignore_errors=True)


def run_night(night: Night, queue: str | None = None, max_jobs: int = MAX_JOBS,
              post: bool = False, write: Callable[[str], None] = print) -> int:
    def log(msg: str) -> None:
        line = f"{datetime.now():%H:%M:%S} {msg}"
        home().mkdir(parents=True, exist_ok=True)
        with open(home() / "night.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
        write(line)
    night.log = log
    if stop_path().exists():
        log("STOP file is there (`megazword night resume` removes it); not starting")
        return 0
    with Lock(home() / "running.lock") as lock:
        if not lock.held:
            log("another night run is going; not starting a second one")
            return 1
        try:
            text, clone, _repo = read_queue(queue)
        except RuntimeError as exc:
            log(f"can't read the queue: {exc}")
            return 1
        state = load_state()
        todo = [j for j in parse_queue(text) if j.mark == " " and j.key not in state]
        log(f"{len(todo)} job(s) waiting; running up to {max_jobs}")
        start_usage = usage_line(night.usage())
        outcomes: list[Outcome] = []
        stopped = ""
        for job in todo:
            if len(outcomes) >= max_jobs:
                stopped = f"hit the {max_jobs}-job cap"
                break
            if stop_path().exists():
                stopped = "STOP file"
                break
            o = night.run_job(job)
            outcomes.append(o)
            log(f"job {o.status}: {job.task} {o.branch} {o.reason}".rstrip())
            if o.status == "skipped" and o.reason.startswith("no AI has room"):
                stopped = "no AI has room left"
                break
            state[job.key] = {"status": o.status, "branch": o.branch, "ai": o.ai,
                              "at": datetime.now().isoformat(timespec="seconds")}
            save_state(state)
        if clone is not None and outcomes:
            try:
                marks = push_queue_marks(clone, text, outcomes, night)
                if marks:
                    log(f"queue marks on {marks}")
            except RuntimeError as exc:
                log(f"queue marks not pushed: {exc}")
        report = summary_text(outcomes, start_usage, usage_line(night.usage()), stopped)
        (home() / f"summary-{night.date}.md").write_text(report, encoding="utf-8")
        log("summary:\n" + report)
        if post and outcomes:
            log("summary posted to Q" if post_to_q(report) else "summary NOT posted (gh missing or failed)")
    return 0


# ---------- scheduled task ----------

def task_command() -> str:
    from .desktop import launcher_python
    return f'"{launcher_python()}" -m megazword.cli night run --post'


def install(at: str = "01:00", yes: bool = False) -> int:
    """Daily task at `at`, windowless (pythonw). Prints the plan; `--yes` creates it."""
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", at):
        print(f"[megazword] --at wants a 24-hour time like 01:00, not '{at}'", file=sys.stderr)
        return 2
    cmd = task_command()
    print(f"[megazword] task {TASK_NAME}: every day at {at}: {cmd}")
    print("[megazword] it runs as you, only while you're signed in (the PC can be locked).")
    if not yes:
        print("[megazword] add --yes to create it")
        return 0
    res = _schtasks(["/Create", "/TN", TASK_NAME, "/SC", "DAILY", "/ST", at, "/TR", cmd, "/F"])
    if res.returncode != 0:
        print(f"[megazword] schtasks failed: {(res.stderr or res.stdout).strip()[:300]}", file=sys.stderr)
        return 1
    print(f"[megazword] scheduled {TASK_NAME} daily at {at}. Off: `megazword night stop` "
          "(skips runs) or `megazword night remove` (deletes the task)")
    return 0


def remove() -> int:
    res = _schtasks(["/Delete", "/TN", TASK_NAME, "/F"])
    if res.returncode != 0:
        print(f"[megazword] schtasks: {(res.stderr or res.stdout).strip()[:300]}", file=sys.stderr)
        return 1
    print(f"[megazword] removed {TASK_NAME}")
    return 0


def status(write: Callable[[str], None] = print) -> int:
    write(f"STOP file: {'yes, night runs are off' if stop_path().exists() else 'no'}")
    write(f"lock: {'a run is going' if (home() / 'running.lock').exists() else 'none'}")
    for name, item in sorted(load_state().items(), key=lambda kv: kv[1].get("at", ""))[-10:]:
        write(f"  {item.get('at', '')} {item.get('status', ''):7} {item.get('branch', '')} {item.get('ai', '')}")
    summaries = sorted(home().glob("summary-*.md"))
    if summaries:
        write(f"last summary: {summaries[-1]}")
    return 0


def add_parser(sub) -> None:
    night = sub.add_parser("night", help="Night Shift: run docs/QUEUE.md jobs unattended on night/ branches")
    nsub = night.add_subparsers(dest="night_cmd", required=True)
    run = nsub.add_parser("run", help="run waiting queue jobs now")
    run.add_argument("--max", type=int, default=MAX_JOBS, help=f"most jobs this run (default {MAX_JOBS})")
    run.add_argument("--job-minutes", type=float, default=JOB_MINUTES, help="AI time cap per job")
    run.add_argument("--floor", type=int, default=FLOOR, help="skip an AI with less than this %% left")
    run.add_argument("--queue", help=f"a local QUEUE.md, or a repo (default {QUEUE_REPO})")
    run.add_argument("--post", action="store_true", help="post the summary to Q (no @-tags)")
    inst = nsub.add_parser("install", help="daily scheduled task (windowless)")
    inst.add_argument("--at", default="01:00", help="24-hour start time (default 01:00)")
    inst.add_argument("--yes", action="store_true", help="really create it")
    nsub.add_parser("remove", help="delete the scheduled task")
    nsub.add_parser("stop", help="stop after the current job and skip future runs (STOP file)")
    nsub.add_parser("resume", help="remove the STOP file")
    nsub.add_parser("status", help="STOP file, lock, recent jobs")


def command(args: argparse.Namespace, cfg: config.Config) -> int:
    if args.night_cmd == "stop":
        home().mkdir(parents=True, exist_ok=True)
        stop_path().write_text(f"stopped {datetime.now():%Y-%m-%d %H:%M}\n", encoding="utf-8")
        print("[megazword] Night Shift stops after the current job and won't start again "
              "until `megazword night resume`")
        return 0
    if args.night_cmd == "resume":
        stop_path().unlink(missing_ok=True)
        print("[megazword] Night Shift is on again")
        return 0
    if args.night_cmd == "status":
        return status()
    if args.night_cmd == "install":
        return install(args.at, args.yes)
    if args.night_cmd == "remove":
        return remove()
    from .backends import default_backends
    backends = default_backends(edit=True, lean=cfg.lean)
    night = Night(backends, floor=args.floor, job_minutes=args.job_minutes)
    write = print if sys.stdout is not None else (lambda s: None)  # pythonw has no console
    return run_night(night, args.queue, args.max, args.post, write)
