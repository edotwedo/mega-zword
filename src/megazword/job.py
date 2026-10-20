"""Split one coding job into pieces. Part 1 is plan-only (`megazword job plan`)."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import config
from .backends import Backend
from .filelock import write_atomic

DIFFICULTY = ("easy", "medium", "hard")
PLANNER_ORDER = ("grok", "claude", "codex")
_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)


@dataclass(frozen=True)
class Piece:
    title: str
    files: tuple[str, ...]
    difficulty: str
    test: str


def jobs_home(home: Path | None = None) -> Path:
    return (home or config.HOME) / "jobs"


def new_id(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{now:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"


def _harder(a: str, b: str) -> str:
    return a if DIFFICULTY.index(a) >= DIFFICULTY.index(b) else b


def merge_overlapping(pieces: list[Piece]) -> list[Piece]:
    """Pieces that share a file become one piece (union of files, harder difficulty)."""
    out = list(pieces)
    changed = True
    while changed:
        changed = False
        merged: list[Piece] = []
        used = [False] * len(out)
        for i, p in enumerate(out):
            if used[i]:
                continue
            files, title, diff, test = set(p.files), p.title, p.difficulty, p.test
            for j in range(i + 1, len(out)):
                if used[j]:
                    continue
                q = out[j]
                if files & set(q.files):
                    used[j] = True
                    files |= set(q.files)
                    title = f"{title}; {q.title}"
                    diff = _harder(diff, q.difficulty)
                    if q.test and q.test not in test:
                        test = f"{test} && {q.test}" if test else q.test
                    changed = True
            merged.append(Piece(title, tuple(sorted(files)), diff, test))
        out = merged
    return out


def _clean_path(raw: str) -> str | None:
    text = str(raw).replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    parts = Path(text).parts
    if not text or text.startswith("/") or ".." in parts:
        return None
    return text


BRIEF_CHARS = 1500  # the brief is resent with every worker's prompt


def parse_plan(text: str) -> tuple[str, list[Piece]]:
    """Planner reply -> (shared brief, pieces). Accepts {"brief", "pieces"} or a bare
    list (plans from before 2026-10-18), so the brief may be empty."""
    blob = text.strip()
    fenced = _FENCE.search(blob)
    if fenced:
        blob = fenced.group(1).strip()
    obj, start = blob.find("{"), blob.find("[")
    if obj >= 0 and (start < 0 or obj < start):
        data = json.loads(blob[obj:blob.rfind("}") + 1])
        if not isinstance(data, dict):
            raise ValueError("planner reply was not a JSON plan")
        brief = " ".join(str(data.get("brief") or "").split())[:BRIEF_CHARS]
        return brief, _pieces(data.get("pieces"))
    end = blob.rfind("]")
    if start < 0 or end <= start:
        raise ValueError("planner reply was not a JSON list of pieces")
    return "", _pieces(json.loads(blob[start:end + 1]))


def parse_pieces(text: str) -> list[Piece]:
    return parse_plan(text)[1]


def _pieces(data) -> list[Piece]:
    if not isinstance(data, list) or not data:
        raise ValueError("planner reply was not a JSON list of pieces")
    pieces: list[Piece] = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("each piece must be an object")
        title = str(item.get("title") or "").strip()
        difficulty = str(item.get("difficulty") or "").strip().lower()
        test = str(item.get("test") or "").strip()
        files = item.get("files")
        if not title or difficulty not in DIFFICULTY:
            raise ValueError("piece needs title and difficulty easy|medium|hard")
        if not isinstance(files, list) or not files:
            raise ValueError("piece needs a files list")
        cleaned = [_clean_path(f) for f in files]
        if any(c is None for c in cleaned):
            raise ValueError("piece files must be relative paths inside the repo")
        pieces.append(Piece(title, tuple(dict.fromkeys(cleaned)), difficulty, test))
    return merge_overlapping(pieces)


def pick_planner(backends: dict[str, Backend]) -> Backend:
    for name in PLANNER_ORDER:
        b = backends.get(name)
        if b is not None and b.available():
            return b
    for b in backends.values():
        if b.available():
            return b
    raise RuntimeError("no installed AI to plan the job")


def planner_prompt(text: str) -> str:
    return (
        "Split this coding job into independent pieces. Reply with JSON only: "
        '{"brief": "...", "pieces": [...]}. brief: under 100 words every worker needs '
        "(goal, shared names, interfaces between pieces). pieces: objects with keys title "
        "(string), files (list of repo-relative paths this piece may edit), difficulty "
        "(easy, medium, or hard), test (command to run for this piece). Merge work that "
        "must touch the same file into one piece. No markdown.\n\n"
        f"Job:\n{text.strip()}"
    )


def save_job(job_id: str, payload: dict, home: Path | None = None) -> Path:
    path = jobs_home(home) / job_id / "job.json"
    write_atomic(path, json.dumps(payload, indent=2) + "\n")
    return path


def format_plan(job_id: str, pieces: list[Piece]) -> str:
    lines = [f"job {job_id}  {len(pieces)} piece" + ("" if len(pieces) == 1 else "s")]
    for i, p in enumerate(pieces, 1):
        files = ", ".join(p.files)
        lines.append(f"{i}. {p.title}  {p.difficulty}  files: {files}  test: {p.test or '(none)'}")
    return "\n".join(lines)


def plan_job(text: str, backends: dict[str, Backend], home: Path | None = None,
             job_id: str | None = None, write: Callable[[str], None] = print) -> int:
    text = (text or "").strip()
    if not text:
        write("job plan: need a job description")
        return 2
    try:
        planner = pick_planner(backends)
    except RuntimeError as exc:
        write(f"job plan: {exc}")
        return 1
    result = planner.run(planner_prompt(text))
    if not result.ok:
        write(f"job plan: {planner.name} failed: {result.error}")
        return 1
    try:
        brief, pieces = parse_plan(result.text)
    except (ValueError, json.JSONDecodeError) as exc:
        write(f"job plan: bad plan from {planner.name}: {exc}")
        return 1
    job_id = job_id or new_id()
    payload = {
        "id": job_id,
        "text": text,
        "planner": planner.name,
        "pieces": [asdict(p) for p in pieces],
    }
    if brief:
        payload["brief"] = brief
    path = save_job(job_id, payload, home)
    write(format_plan(job_id, pieces))
    write(f"saved {path}")
    return 0


def add_parser(sub) -> None:
    job = sub.add_parser("job", help="split a coding job for parallel workers (plan first)")
    jsub = job.add_subparsers(dest="job_cmd", required=True)
    plan = jsub.add_parser("plan", help="ask one AI to split a job into pieces")
    plan.add_argument("text", help="the job to split")
    run = jsub.add_parser("run", help="execute a planned job on multiple workers")
    run.add_argument("id", help="job ID from `megazword job plan`")
    run.add_argument("--workers", "-w", type=int, default=2, help="number of parallel workers (1-8)")
    run.add_argument("--repo", help="repo URL to clone (default: local Gitea mega-zword URL)")
    status = jsub.add_parser("status", help="show a job's pieces: status, tests, AIs, branch")
    status.add_argument("id", help="job ID from `megazword job plan`")
    cost = jsub.add_parser("cost", help="tokens and steps per model for a saved job, from the run log")
    cost.add_argument("id", help="job ID from `megazword job plan`")
    jsub.add_parser("scores", help="which AI delivers passing pieces, from every saved job")
    combine = jsub.add_parser("combine", help="merge a job's passed pieces on job/ID, test and review it")
    combine.add_argument("id", help="job ID from `megazword job plan`")
    combine.add_argument("--no-push", action="store_true", help="keep job/ID local")


def run_job(job_id: str, workers: int, repo: str | None, cfg: config.Config,
            backends: dict[str, Backend], write: Callable[[str], None] = print) -> int:
    """`megazword job run ID`: run a saved plan's pieces, one line per piece."""
    from . import job_workers
    path = jobs_home() / job_id / "job.json"
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        write(f"job run: no job {job_id} (make one with `megazword job plan`)")
        return 1
    except (OSError, ValueError) as exc:
        write(f"job run: can't read {path}: {exc}")
        return 1
    if not isinstance(plan.get("pieces"), list) or not plan["pieces"]:
        write(f"job run: job {job_id} has no pieces")
        return 1
    if repo is None:
        from .heartbeat import GITEA
        repo = GITEA
    try:
        report = job_workers.run_pieces(plan, repo, job_id=job_id, workers=workers,
                                        cfg=cfg, backends=backends)
    except (ValueError, RuntimeError, OSError) as exc:
        write(f"job run: {exc}")
        return 1
    for row in report.get("results", []):
        line = f"{row.get('index')}. {row.get('title', '')}  {row.get('status', '')}  {row.get('ai') or '-'}"
        if row.get("reason"):
            line += f"  ({row['reason']})"
        write(line)
    return 0 if report.get("runner_status") == "complete" else 1


def format_status(report: dict) -> str:
    """One job's state: overall runner_status, then one block per piece. A plan that
    hasn't run has no runner_status and no results, so every piece is "not started"."""
    results = {row.get("index"): row for row in report.get("results") or []}
    pieces = report.get("pieces") or []
    lines = [f"job {report.get('id', '?')}: {report.get('runner_status') or 'not started'}"]
    for index, piece in enumerate(pieces, 1):
        row = results.get(index, {})
        lines.append(f"{index}. {piece.get('title', '')}  {row.get('status') or 'not started'}")
        if not row:
            continue
        details = [("tests", row.get("tests")), ("delivered by", row.get("ai")),
                   ("tried", ", ".join(row.get("tried") or [])), ("branch", row.get("branch")),
                   ("reason", row.get("reason"))]
        lines += [f"   {label}: {value}" for label, value in details if value]
    return "\n".join(lines)


def status_job(job_id: str, write: Callable[[str], None] = print) -> int:
    """`megazword job status ID`: read the saved job; never runs anything."""
    path = jobs_home() / job_id / "job.json"
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        write(f"job status: no job {job_id} (make one with `megazword job plan`)")
        return 1
    except (OSError, ValueError) as exc:
        write(f"job status: can't read {path}: {exc}")
        return 1
    write(format_status(report))
    return 0


def command(args, backends: dict[str, Backend], cfg: config.Config,
            write: Callable[[str], None] = print) -> int:
    if args.job_cmd == "status":
        return status_job(args.id, write=write)
    if args.job_cmd == "cost":
        from . import job_cost
        return job_cost.cost_job(args.id, write=write)
    if args.job_cmd == "scores":
        from . import scores
        write(scores.format_scores(scores.scoreboard(scores.load_reports(jobs_home()))))
        return 0
    if args.job_cmd == "plan":
        return plan_job(args.text, backends, write=write)
    if args.job_cmd == "run":
        return run_job(args.id, args.workers, args.repo, cfg, backends, write=write)
    if args.job_cmd == "combine":
        from . import team
        try:
            combined = team.combine(args.id, backends, cfg, push=not args.no_push)
        except FileNotFoundError as exc:
            write(f"job combine: {exc}")
            return 1
        write(team.format_combined(combined))
        return 0 if combined["status"].startswith("ready") else 1
    write("Usage: megazword job plan \"...\"")
    return 2
