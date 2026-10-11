"""Append-only JSON-lines files (run log, project memory) with a size cap.

Files are trimmed to the newest `keep` lines once they grow 20% past it, so
the rewrite happens rarely, not on every append.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

DEFAULT_LOG_LINES = 5000
# Cheap pre-check: only count lines once the file is big enough to matter.
_BYTES_PER_LINE_GUESS = 120


def append(path: Path, max_lines: int = DEFAULT_LOG_LINES, **record) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), **record}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    trim(path, max_lines)


def trim(path: Path, keep: int, protect: Callable[[str], bool] | None = None) -> bool:
    """Keep the newest `keep` lines. Lines where protect(line) is true are
    always kept (and don't count toward `keep`). Returns True if trimmed."""
    if keep <= 0 or not path.exists():
        return False
    if path.stat().st_size < keep * _BYTES_PER_LINE_GUESS:
        return False
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    protected = [protect(line) for line in lines] if protect else [False] * len(lines)
    trimmable = protected.count(False)
    if trimmable <= keep * 1.2:
        return False
    drop = trimmable - keep
    kept = []
    for line, safe in zip(lines, protected):
        if not safe and drop > 0:
            drop -= 1
            continue
        kept.append(line)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(kept) + "\n", encoding="utf-8")
    os.replace(tmp, path)  # atomic: a crash never leaves a half-written file
    return True
