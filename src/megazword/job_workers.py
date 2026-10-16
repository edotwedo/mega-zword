"""Part 2 of megazword job: execute independent planned pieces.

Planning and combining/review are separate stages. Each piece gets one worktree
and one worker; this runner owns git, tests and commits, and never touches main.
"""
from __future__ import annotations

import json
import math
import os
import re
import shlex
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath

from . import config, night
from .agent import AgentBackend, wrap
from .backends import Backend, CLIBackend, OllamaBackend, default_backends, apply_levels
from .filelock import write_atomic
from .free_apis import OpenAICompatibleBackend
from .guard import scrub
from .log import append
from .agent_quality import check_tests, is_test_path
from .routing import tencent_first


def _safe(text):
    text = str(text)
    for name, value in sorted(os.environ.items(), key=lambda item: -len(item[1])):
        if value and (re.search(r"KEY|TOKEN|SECRET|PASSWORD", name, re.I) or name == "CLOUDFLARE_ACCOUNT_ID"):
            text = text.replace(value, "[REDACTED]")
    return scrub(text)


@dataclass(frozen=True)
class Piece:
    title: str
    files: tuple[str, ...]
    difficulty: str
    test: tuple[str, ...] = ()


@dataclass
class PieceResult:
    index: int
    title: str
    status: str = "failed"
    ai: str = ""
    branch: str = ""
    commit: str = ""
    tests: str = ""
    reason: str = ""
    seconds: float = 0
    requests: int = 0
    est_tokens: int = 0
    tried: list[str] | None = None


def _file(value: str) -> str:
    if not isinstance(value, str) or not value or any(c in value for c in "\\:*?[]\0\n\r"):
        raise ValueError("piece files must be explicit relative paths, not globs")
    path = PurePosixPath(value)
    if PureWindowsPath(value).is_reserved():
        raise ValueError("reserved Windows path refused")
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("piece file escapes the work folder")
    if any(p.lower() == ".git" or p.lower().startswith(".env") for p in path.parts):
        raise ValueError("private git/environment files are refused")
    if night.SECRET_FILES.search(value) or "common-ground/private" in value.lower():
        raise ValueError("private files are refused")
    if any(p.endswith((".", " ")) for p in path.parts):
        raise ValueError("ambiguous Windows path refused")
    return path.as_posix()


def _pytest_args(args, work=None):
    """Allow selectors and a small set of reporting options, never path options."""
    flags = {"-q", "-qq", "-v", "-vv", "-x", "-s", "--disable-warnings",
             "--strict-markers", "--strict-config", "--collect-only", "--no-header", "--no-summary"}
    values = {"-k", "-m", "--maxfail", "--tb", "--capture", "--durations", "-p"}
    i = 0
    while i < len(args):
        arg = args[i]
        option, sep, value = arg.partition("=")
        if arg in flags:
            i += 1
            continue
        if option in values:
            if not sep:
                i += 1
                if i == len(args):
                    raise ValueError("missing pytest option value")
                value = args[i]
            if not value or (option in {"--maxfail", "--durations"} and not value.isdigit()):
                raise ValueError("invalid pytest option value")
            if option == "--tb" and value not in {"auto", "long", "short", "line", "native", "no"}:
                raise ValueError("invalid pytest traceback style")
            if option == "--capture" and value not in {"fd", "sys", "no", "tee-sys"}:
                raise ValueError("invalid pytest capture mode")
            if option == "-p" and value != "no:cacheprovider":
                raise ValueError("pytest plugin loading is refused")
        elif arg.startswith("-"):
            raise ValueError("unsupported pytest option; path and plugin options are refused")
        else:
            target = arg.split("::", 1)[0]
            if target.startswith("@"):
                raise ValueError("pytest argument files are refused")
            if target != ".":
                _file(target)
            if work is not None and not (work / target).resolve().is_relative_to(work.resolve()):
                raise ValueError("pytest target escapes the work folder")
        i += 1


def _test(value) -> tuple[str, ...]:
    if not value:
        return ()
    args = shlex.split(value) if isinstance(value, str) else value
    if not isinstance(args, (list, tuple)) or not args or any(not isinstance(a, str) for a in args):
        raise ValueError("test must be a command string or argument list")
    # The planner supplies a test command, not an arbitrary shell. Python tests
    # still execute repository code; Night Shift's stripped environment applies.
    if any(any(c in a for c in ";&|`\n\r\0") for a in args):
        raise ValueError("shell operators are not allowed in test commands")
    exe = Path(args[0]).name.lower()
    if exe in ("python", "python3", "python.exe", "python3.exe"):
        if args[1:3] != ["-m", "pytest"] and tuple(args[1:3]) != ("-m", "pytest"):
            raise ValueError("Python test commands must use -m pytest")
        _pytest_args(args[3:])
        return (sys.executable, *args[1:])
    if exe in ("pytest", "pytest.exe"):
        _pytest_args(args[1:])
        return (sys.executable, "-m", "pytest", *args[1:])
    if exe in ("npm", "npm.cmd") and tuple(args[1:]) in (("test",), ("run", "typecheck")):
        return tuple(args)
    raise ValueError("supported tests: python -m pytest, pytest, npm test, npm run typecheck")


def validate_pieces(plan: dict) -> list[Piece]:
    rows = plan.get("pieces") if isinstance(plan, dict) else None
    if not isinstance(rows, list) or not rows or len(rows) > 32:
        raise ValueError("plan needs 1 to 32 pieces")
    seen, pieces = set(), []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("title"), str) or not row["title"].strip():
            raise ValueError("each piece needs a title")
        files = row.get("files")
        if not isinstance(files, list) or not files:
            raise ValueError("each piece needs its files")
        paths = tuple(_file(f) for f in files)
        keys = [p.casefold() for p in paths]
        if len(set(keys)) != len(keys) or seen.intersection(keys):
            raise ValueError("overlapping files: merge these pieces in the planner before running")
        seen.update(keys)
        level = row.get("difficulty")
        if level not in ("easy", "medium", "hard"):
            raise ValueError("piece difficulty must be easy, medium or hard")
        pieces.append(Piece(row["title"].strip(), paths, level,
                            _test(row.get("test", row.get("test_command", "")))))
    return pieces


def _free(backend: Backend) -> bool:
    return isinstance(backend, (OpenAICompatibleBackend, OllamaBackend))


class Runner:
    def __init__(self, cfg: config.Config, backends: dict[str, Backend],
                 usage=night.live_summaries, job_minutes=30, test_minutes=20):
        self.cfg, self.backends, self.usage = cfg, backends, usage
        self.seconds, self.test_seconds = job_minutes * 60, test_minutes * 60
        self._route_lock = threading.Lock()
        self._reserved: set[str] = set()

    def _reserve(self, piece: Piece):
        # Live meter reads and reservations happen serially. A paid CLI gets at
        # most one concurrent piece. Free HTTP calls share the coding loop's pace.
        with self._route_lock:
            summaries = self.usage()
            paid, _ = night.eligible(self.backends, summaries)
            paid = [n for n in paid if isinstance(self.backends[n], CLIBackend)
                    and n not in self._reserved and n not in self.cfg.out_now()]
            order = tencent_first(
                self.cfg.agent.get("failover_order", config.DEFAULT_FREE_FAILOVER),
                self.cfg.log_path)
            names = list(dict.fromkeys([*order, "ollama"]))
            free = [self.backends[n] for n in names if n in self.backends
                    and _free(self.backends[n]) and n not in self.cfg.out_now()
                    and self.backends[n].available()]
            if free:
                # Give zero-cost workers first pass at every difficulty. One
                # paid retry is still owned by the runner if that loop fails.
                return free, paid
            if paid:
                return [], paid
            return [], []

    def _worker(self, work: Path, piece: Piece, free: list[Backend], paid: str | None):
        if free:
            settings = dict(self.cfg.agent)
            settings.update(root=work, wall_timeout=min(self.seconds, settings.get("wall_timeout", 600)),
                            reviewer="", allow_test_edits=bool(re.search(
                                r"\b(?:tests?|testing|pytest|unittest)\b", piece.title, re.I)))
            if piece.test:
                settings["test_command"] = piece.test
            return wrap(replace(free[0]), settings, fallback_backends=[replace(b) for b in free[1:]])
        selected = {paid: replace(self.backends[paid])}
        apply_levels(selected, piece.difficulty, self.cfg.grok, self.cfg.levels)
        source = selected[paid]
        return replace(source, cwd=str(work), timeout=min(source.timeout, int(self.seconds)))

    def run_piece(self, clone: Path, folder: Path, job_id: str, index: int, piece: Piece,
                  base: str) -> PieceResult:
        import time
        started = time.monotonic()
        result = PieceResult(index, piece.title, tried=[])
        branch = f"job/{job_id}-{index}"
        work = folder / f"piece-{index}"
        held = None
        try:
            free, paid = self._reserve(piece)
            if not free and not paid:
                result.status, result.reason = "skipped", "no available worker with fresh usage and spare capacity"
                return result
            night._check(night.git(["worktree", "add", "--quiet", "-b", branch, str(work), base], clone), "worktree")
            original = night._check(night.git(["rev-parse", "HEAD"], work), "HEAD").strip()
            prompt = (f"Work on this independent piece only: {piece.title}\n"
                      f"Allowed files (exact paths): {', '.join(piece.files)}\n"
                      "Edit only those files. Do not run git, commit, push or change unrelated files. "
                      "Mega Zword owns git and runs the tests. Keep the change small. Finish with a short summary.")
            # Any piece may get one paid retry after its free loop fails.
            attempts = [(free, None)] if free else []
            if paid:
                attempts.append(([], paid[0]))
            for options, name in attempts:
                if name:
                    with self._route_lock:
                        # Recheck usage after a free attempt; never use a stale
                        # capacity snapshot to spend a paid retry.
                        allowed, _ = night.eligible(self.backends, self.usage())
                        name = next((n for n in paid if n in allowed
                                     and n not in self._reserved and n not in self.cfg.out_now()), None)
                        if name is None:
                            result.reason = "paid retry has no current capacity"
                            continue
                        self._reserved.add(name)
                        held = name
                worker = self._worker(work, piece, options, name)
                answer = worker.run(prompt)
                used = getattr(worker, "backends_used", None) or [worker.name]
                result.tried.extend(used)
                requests = max(1, getattr(worker, "request_count", 1))
                result.requests += requests
                chars = getattr(worker, "prompt_chars", len(prompt)) + getattr(worker, "answer_chars", len(answer.text))
                result.est_tokens += (chars + 3) // 4
                append(self.cfg.log_path, backend=worker.name, project=job_id,
                       forced=False, ok=answer.ok, seconds=answer.seconds,
                       prompt_chars=getattr(worker, "prompt_chars", len(prompt)),
                       answer_chars=getattr(worker, "answer_chars", len(answer.text)), requests=requests,
                       backends_used=used, final_backend=used[-1],
                       requests_by_backend=getattr(worker, "requests_by_backend", None) or {worker.name: 1},
                       est_tokens=(chars + 3) // 4)
                if night._check(night.git(["rev-parse", "HEAD"], work), "HEAD").strip() != original:
                    result.reason = "worker changed git HEAD; no commit retained"
                    return result
                if night._check(night.git(["symbolic-ref", "--short", "HEAD"], work), "branch").strip() != branch:
                    result.reason = "worker changed git branch; not delivered"
                    return result
                night._check(night.git(["add", "-A"], work), "stage")
                names = [n for n in night._check(night.git(["diff", "--cached", "--name-only", "-z"], work), "changed files").split("\0") if n]
                unexpected = [n for n in names if n.casefold() not in {f.casefold() for f in piece.files}]
                problem = night.secret_problem(work)
                if unexpected or problem:
                    result.reason = problem or "worker edited files outside its piece: " + ", ".join(unexpected)
                    return result
                if not answer.ok or not names:
                    result.reason = _safe(answer.error or "worker made no changes")
                    night._check(night.git(["reset", "--hard", "--quiet", original], work), "reset failed attempt")
                    night._check(night.git(["clean", "-fdq"], work), "clean failed attempt")
                    continue
                for path in names:
                    if is_test_path(Path(path)) and (work / path).exists():
                        errors = check_tests((work / path).read_text(encoding="utf-8"), path)
                        if errors:
                            result.reason = "test quality gate: " + "; ".join(errors)
                            return result
                # Test exactly the worker's staged tree. Test outputs never join
                # this commit, and a test that changes HEAD invalidates delivery.
                night._check(night.git(["-c", "core.hooksPath=", "commit", "--quiet", "-m",
                                       f"job {job_id}: {piece.title[:80]}"], work), "commit")
                tested = night._check(night.git(["rev-parse", "HEAD"], work), "HEAD").strip()
                cmd, env = night.test_command(work, night.Job(0, " ", "", piece.title, "piece passes"))
                if piece.test:
                    cmd = list(piece.test)
                    env = night.test_env(work)
                    if (work / "src").is_dir():
                        env["PYTHONPATH"] = os.pathsep.join(
                            [str(work / "src"), env.get("PYTHONPATH", "")]).strip(os.pathsep)
                if cmd:
                    if cmd[1:3] == ["-m", "pytest"]:
                        _pytest_args(cmd[3:], work)
                    checked = night.run_cmd(cmd, work, self.test_seconds, env)
                    result.tests = "passed" if checked.returncode == 0 else "failed"
                    if checked.returncode:
                        result.reason = "tests failed: " + _safe((checked.stdout or checked.stderr))[-1000:]
                        if options and paid:
                            night._check(night.git(["reset", "--hard", "--quiet", original], work), "reset failed tests")
                            night._check(night.git(["clean", "-fdq"], work), "clean test output")
                            continue
                        return result
                else:
                    result.tests = "none"
                if night._check(night.git(["rev-parse", "HEAD"], work), "HEAD").strip() != tested:
                    result.reason = "tests changed HEAD; not delivered"
                    return result
                if night._check(night.git(["symbolic-ref", "--short", "HEAD"], work), "branch").strip() != branch:
                    result.reason = "tests changed git branch; not delivered"
                    return result
                if night.git(["diff", "--quiet"], work).returncode != 0 or night.git(["diff", "--cached", "--quiet"], work).returncode != 0:
                    result.reason = "tests changed tracked files; not delivered"
                    return result
                if night.secret_problem(work, since=original):
                    result.reason = "committed change failed the secret scan"
                    return result
                result.status, result.ai, result.branch, result.commit = "passed", used[-1], branch, tested
                result.reason = ""
                return result
            return result
        except Exception as error:
            result.reason = _safe(error)[:1500]
            return result
        finally:
            if held:
                with self._route_lock:
                    self._reserved.discard(held)
            result.seconds = round(time.monotonic() - started, 3)


def run_pieces(plan: dict, repo: str | Path, *, job_id: str | None = None,
               workers: int = 2, cfg: config.Config | None = None,
               backends: dict[str, Backend] | None = None, usage=night.live_summaries,
               job_minutes=30, test_minutes=20) -> dict:
    """Execute a validated hand-written or saved plan; return its persisted report.

    No merge or push: the planner/combiner owns review and final publication.
    Completed IDs are idempotent. Failed worktrees remain available for inspection.
    """
    pieces = validate_pieces(plan)
    if type(workers) is not int or not 1 <= workers <= 8:
        raise ValueError("workers must be 1 to 8")
    if any(not math.isfinite(v) or v <= 0 for v in (job_minutes, test_minutes)):
        raise ValueError("timeouts must be positive")
    job_id = job_id or plan.get("id") or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", job_id):
        raise ValueError("invalid job ID")
    cfg = cfg or config.load()
    folder = config.HOME / "jobs" / job_id
    folder.mkdir(parents=True, exist_ok=True)
    report_path = folder / "job.json"
    with night.Lock(folder / "runner.lock") as lock:
        if not lock.held:
            raise RuntimeError("this job already has a worker runner")
        if report_path.exists():
            previous = json.loads(report_path.read_text(encoding="utf-8"))
            if previous.get("runner_status") in ("complete", "failed"):
                if (previous.get("repo") != str(repo) or previous.get("pieces") !=
                        json.loads(json.dumps([asdict(p) for p in pieces]))):
                    raise ValueError("job ID already belongs to a different plan")
                return previous
            if previous.get("runner_status") == "running":
                raise RuntimeError("interrupted job needs explicit recovery; refusing duplicate workers")
        if backends is None:
            backends = default_backends(edit=True, free_models=cfg.free, lean=cfg.lean)
            backends["ollama"] = OllamaBackend("ollama", model=cfg.free.get("ollama", "qwen2.5-coder:7b"))
        clone = folder / "repo"
        if clone.exists():
            raise RuntimeError("job repo already exists; refusing to overwrite it")
        night._check(night.run_cmd(["git", "clone", "--quiet", night.remote_url(str(repo)), str(clone)], timeout=600), "clone")
        base = night._check(night.git(["rev-parse", night.default_branch(clone)], clone), "base commit").strip()
        report = dict(plan)  # retain the planner's prompt and attribution
        report.update({"id": job_id, "repo": str(repo), "base": base, "clone": str(clone),
                       "pieces": json.loads(json.dumps([asdict(p) for p in pieces])),
                       "runner_status": "running", "results": []})
        def save():
            write_atomic(report_path, json.dumps(report, indent=2))
        save()
        runner = Runner(cfg, backends, usage, job_minutes, test_minutes)
        with ThreadPoolExecutor(max_workers=min(workers, len(pieces))) as pool:
            futures = [pool.submit(runner.run_piece, clone, folder, job_id, i, piece, base)
                       for i, piece in enumerate(pieces, 1)]
            for future in as_completed(futures):
                report["results"].append(asdict(future.result()))
                report["results"].sort(key=lambda row: row["index"])
                save()
        report["runner_status"] = "complete" if all(r["status"] == "passed" for r in report["results"]) else "failed"
        save()
        return report
