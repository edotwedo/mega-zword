"""Append-only run log: one JSON object per line. Start of usage tracking."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def append(path: Path, **record) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), **record}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
