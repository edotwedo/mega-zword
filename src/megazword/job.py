"""Plan a coding job. This step does not run workers or test commands."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from . import config
from .backends import Backend
from .filelock import write_atomic
from .job_workers import _file, _safe, _test, validate_pieces


PROMPT = """Plan this coding job; do not edit files or execute commands.
Split it into 1 to 32 independent pieces. Use explicit repository-relative file
paths with forward slashes, not folders or globs. Pieces sharing a file belong
together. Each piece needs a title, files, difficulty (easy/medium/hard), and
a test command (python -m pytest, pytest, npm test, or npm run typecheck).
Reply with JSON only, in this form:
{{"pieces": [{{"title": "...", "files": ["src/example.py"],
"difficulty": "medium", "test": "python -m pytest -q"}}]}}

Job:
{text}
"""


def validate_plan(data) -> dict:
    """Validate and merge connected sets of overlapping files, including on Windows."""
    rows = data.get("pieces") if isinstance(data, dict) else data
    if not isinstance(rows, list) or not 1 <= len(rows) <= 32:
        raise ValueError("plan needs 1 to 32 pieces")
    pieces = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each piece must be an object")
        for field in ("title", "difficulty", "test"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(f"each piece needs a nonempty {field}")
        if row["difficulty"] not in ("easy", "medium", "hard"):
            raise ValueError("piece difficulty must be easy, medium or hard")
        if not isinstance(row.get("files"), list) or not row["files"]:
            raise ValueError("each piece needs its files")
        files = {}
        for value in row["files"]:
            path = _file(value)
            files.setdefault(path.casefold(), path)
        _test(row["test"])
        pieces.append({"title": row["title"].strip(), "files": list(files.values()),
                       "difficulty": row["difficulty"], "test": row["test"].strip()})

    # Grow each component until no later piece intersects it; a bridge can join
    # pieces that did not overlap when first encountered.
    merged = []
    while pieces:
        group = [pieces.pop(0)]
        files = {f.casefold(): f for f in group[0]["files"]}
        changed = True
        while changed:
            changed = False
            for piece in pieces[:]:
                if files.keys() & {f.casefold() for f in piece["files"]}:
                    group.append(piece)
                    for path in piece["files"]:
                        files.setdefault(path.casefold(), path)
                    pieces.remove(piece)
                    changed = True
        tests = list(dict.fromkeys(p["test"] for p in group))
        test = tests[0]
        if len(tests) > 1:
            if all(_test(t)[1:3] == ("-m", "pytest") for t in tests):
                # Run the whole suite rather than dropping any component's tests
                # or combining incompatible pytest options.
                test = "python -m pytest"
            else:
                raise ValueError("overlapping pieces need compatible test commands")
        merged.append({"title": "; ".join(p["title"] for p in group),
                       "files": list(files.values()),
                       "difficulty": max((p["difficulty"] for p in group),
                                         key=("easy", "medium", "hard").index),
                       "test": test})
    plan = {"pieces": merged}
    validate_pieces(plan)  # Keep the saved plan compatible with the worker runner.
    return plan


def plan(text: str, backend: Backend) -> dict:
    """Ask one AI once, validate its JSON, then save HOME/jobs/ID/job.json."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("job text must not be empty")
    text = _safe(text.strip())
    result = backend.run(PROMPT.format(text=text))
    if not result.ok:
        raise ValueError(f"planner failed: {_safe(result.error)}")
    raw = _safe(result.text.strip())
    if raw.startswith("```json\n") and raw.endswith("\n```"):
        raw = raw[8:-4]
    try:
        saved = validate_plan(json.loads(raw))
    except json.JSONDecodeError:
        raise ValueError("planner did not return valid JSON") from None
    saved.update(id=uuid.uuid4().hex, job=text, planner=backend.name, status="planned",
                 created_at=datetime.now(timezone.utc).isoformat())
    path = config.HOME / "jobs" / saved["id"] / "job.json"
    write_atomic(path, json.dumps(saved, indent=2, ensure_ascii=False) + "\n")
    return saved
