"""Past answers: the last few prompts and final answers, for the dashboard.

Stored in ~/.megazword/answers.jsonl and trimmed so it never grows large.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import config

KEEP = 50
_lock = threading.Lock()


@contextmanager
def _writer_lock(p: Path):
    # Dashboard jobs are separate CLI processes. A thread lock alone loses writes.
    with _lock, p.with_suffix(".lock").open("a+b") as lock:
        if os.name == "nt":
            import msvcrt
            if lock.seek(0, os.SEEK_END) == 0:
                lock.write(b"\0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def path() -> Path:
    return config.HOME / "answers.jsonl"


def add(prompt: str, answer: str, backend: str, project: str, rating: str | None,
        keep: int = KEEP) -> None:
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    record = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "backend": backend, "project": project, "rating": rating,
              "prompt": prompt, "answer": answer}
    if keep < 1:
        raise ValueError("keep must be positive")
    with _writer_lock(p):
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines() if p.exists() else []
        lines = [*lines, json.dumps(record)][-keep:]
        # Readers see a complete old or new file, never a truncate/partial write.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=p.parent,
                                         delete=False) as temp:
            staged = Path(temp.name)
            temp.write("\n".join(lines) + "\n")
        try:
            os.replace(staged, p)
        finally:
            staged.unlink(missing_ok=True)


def recent(n: int = 20) -> list[dict]:
    """Newest first; skips damaged lines."""
    p = path()
    if not p.exists():
        return []
    out = []
    # Windows cannot replace a file while another process has it open.
    with _writer_lock(p):
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    for line in lines:
        try:
            record = json.loads(line)
            if isinstance(record, dict):
                out.append(record)
        except ValueError:
            continue
    return list(reversed(out))
