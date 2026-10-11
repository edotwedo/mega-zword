"""Shared project memory: notes, decisions and a who-did-what log.

This is what replaces the old Hive message board. Every AI that Mega Zword
runs can be handed the recent entries as context, so no AI has to go read a
board or guess what the others did.

Stored per project as JSON lines in ~/.megazword/projects/<project>/memory.jsonl.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .log import trim

KINDS = ("note", "decision", "done")
DEFAULT_MEMORY_LINES = 2000


@dataclass
class Entry:
    time: str
    kind: str
    text: str
    by: str


def project_name(cwd: Path | None = None) -> str:
    """Git repo folder name if inside one, else the current folder name."""
    cwd = cwd or Path.cwd()
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd,
                             capture_output=True, text=True, timeout=5)
        if top.returncode == 0 and top.stdout.strip():
            cwd = Path(top.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return re.sub(r"[^A-Za-z0-9._-]", "_", cwd.name) or "default"


class Memory:
    def __init__(self, home: Path, project: str, max_lines: int = DEFAULT_MEMORY_LINES):
        self.project = project
        self.max_lines = max_lines
        self.path = home / "projects" / project / "memory.jsonl"

    def add(self, kind: str, text: str, by: str = "phil", time: str | None = None) -> Entry:
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}")
        entry = Entry(time or datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      kind, text.strip(), by)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry)) + "\n")
        return entry

    def entries(self) -> list[Entry]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(Entry(**json.loads(line)))
        return out

    def recent(self, n: int = 10, kinds: tuple[str, ...] = KINDS) -> list[Entry]:
        return [e for e in self.entries() if e.kind in kinds][-n:]

    def context_block(self, n: int = 10, max_decisions: int = 15,
                      max_chars: int = 300) -> str:
        """Recent memory formatted for the top of a prompt: the newest
        decisions (they're the rules), then recent notes and done items.
        Capped so context never eats much of a paid plan's usage."""
        entries = self.entries()
        decisions = sorted((e for e in entries if e.kind == "decision"),
                           key=lambda e: e.time)[-max_decisions:]
        others = [e for e in entries if e.kind != "decision"][-n:]
        if not decisions and not others:
            return ""
        lines = [f"[Project memory for '{self.project}', kept by Mega Zword]"]
        if decisions:
            lines.append("Decisions (follow these):")
            lines += [f"- {_clip(e.text, max_chars)}" for e in decisions]
        if others:
            lines.append("Recent activity:")
            lines += [f"- {e.time[:16]} {e.by} {e.kind}: {_clip(e.text, max_chars)}"
                      for e in others]
        return "\n".join(lines)


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def with_context(prompt: str, block: str) -> str:
    return f"{block}\n\n[Task]\n{prompt}" if block else prompt
