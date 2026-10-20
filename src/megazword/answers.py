"""Past answers: the last few prompts and final answers, for the dashboard.

Stored in ~/.megazword/answers.jsonl and trimmed so it never grows large.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .filelock import locked, write_atomic

KEEP = 50


def path() -> Path:
    return config.HOME / "answers.jsonl"


def add(prompt: str, answer: str, backend: str, project: str, rating: str | None,
        keep: int = KEEP, tab_id: str | None = None) -> None:
    if keep < 1:
        raise ValueError("keep must be positive")
    p = path()
    record = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "backend": backend, "project": project, "rating": rating,
              "prompt": prompt, "answer": answer}
    if tab_id:
        record["tab_id"] = tab_id
    with locked(p):  # parallel dashboard jobs can finish at the same moment
        lines = (p.read_text(encoding="utf-8", errors="replace").splitlines()
                 if p.exists() else [])
        lines = [*lines, json.dumps(record)][-keep:]
        write_atomic(p, "\n".join(lines) + "\n")


def recent(n: int = 20, project: str | None = None) -> list[dict]:
    """Newest first; skips damaged lines and non-object records. With
    `project`, only that project's answers."""
    p = path()
    if not p.exists():
        return []
    # Windows can't os.replace a file another process has open, so readers
    # take the same lock as writers.
    with locked(p):
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    out = []
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict) and (project is None or record.get("project") == project):
            out.append(record)
    return list(reversed(out[-n:]))
