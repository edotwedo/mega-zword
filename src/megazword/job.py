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


def parse_pieces(text: str) -> list[Piece]:
    blob = text.strip()
    fenced = _FENCE.search(blob)
    if fenced:
        blob = fenced.group(1).strip()
    start, end = blob.find("["), blob.rfind("]")
    if start < 0 or end <= start:
        raise ValueError("planner reply was not a JSON list of pieces")
    data = json.loads(blob[start:end + 1])
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
        "Split this coding job into independent pieces. Reply with JSON only: a list of "
        "objects with keys title (string), files (list of repo-relative paths this piece "
        "may edit), difficulty (easy, medium, or hard), test (command to run for this "
        "piece). Merge work that must touch the same file into one piece. No markdown.\n\n"
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
        pieces = parse_pieces(result.text)
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
    path = save_job(job_id, payload, home)
    write(format_plan(job_id, pieces))
    write(f"saved {path}")
    return 0


def add_parser(sub) -> None:
    job = sub.add_parser("job", help="split a coding job for parallel workers (plan first)")
    jsub = job.add_subparsers(dest="job_cmd", required=True)
    plan = jsub.add_parser("plan", help="ask one AI to split a job into pieces")
    plan.add_argument("text", help="the job to split")


def command(args, backends: dict[str, Backend], cfg: config.Config,
            write: Callable[[str], None] = print) -> int:
    if args.job_cmd == "plan":
        return plan_job(args.text, backends, write=write)
    write("Usage: megazword job plan \"...\"")
    return 2
