"""One-time import from the old Hive workshop repo into Mega Zword memory.

Reads a local clone (read-only): DECISIONS.md bullets become decisions with
their original dates, and handoffs whose Status isn't done/parked become
notes. The old repo is never modified.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .memory import Memory

DECISION_LINE = re.compile(r"^- (\d{4}-\d{2}-\d{2}): (.+)$")
FIELD = re.compile(r"^- \*\*(\w[\w ]*):\*\*\s*(.*)$")
CLOSED = ("done", "parked")
SKIP_FILES = {"README.md", "TEMPLATE.md"}


@dataclass
class Handoff:
    file: str
    title: str
    status: str
    owner: str
    job: str


def parse_decisions(text: str) -> list[tuple[str, str]]:
    """(date, text) for each dated decision bullet, oldest first."""
    found = []
    for line in text.splitlines():
        m = DECISION_LINE.match(line.strip())
        if m:
            found.append((m.group(1), m.group(2).replace("**", "").strip()))
    return sorted(found, key=lambda d: d[0])


def parse_handoff(name: str, text: str) -> Handoff | None:
    """None if the file isn't in handoff format."""
    lines = text.splitlines()
    title = next((l[2:].strip() for l in lines if l.startswith("# ")), "")
    if not title:
        return None
    fields = {}
    for line in lines:
        m = FIELD.match(line.strip())
        if m:
            fields[m.group(1).lower()] = m.group(2).strip()
    if "status" not in fields:
        return None
    job = ""
    if "## The job" in text:
        after = text.split("## The job", 1)[1].split("\n## ", 1)[0]
        job = " ".join(after.split())
    return Handoff(name, title.removeprefix("Handoff:").strip(), fields["status"],
                   fields.get("for", ""), job[:300])


def open_handoffs(folder: Path) -> list[Handoff]:
    out = []
    for path in sorted(folder.glob("*.md")):
        if path.name in SKIP_FILES:
            continue
        h = parse_handoff(path.name, path.read_text(encoding="utf-8", errors="replace"))
        if h and not h.status.lower().startswith(CLOSED):
            out.append(h)
    return out


def import_hive(repo: Path, memory: Memory) -> tuple[int, int]:
    """Import into `memory`. Returns (decisions, handoffs) added. Entries
    already imported (same text) are skipped, so re-running is safe."""
    existing = {e.text for e in memory.entries()}
    decisions = handoffs = 0
    decisions_file = repo / "DECISIONS.md"
    if decisions_file.exists():
        for date, text in parse_decisions(decisions_file.read_text(encoding="utf-8")):
            entry = f"{date}: {text}"
            if entry not in existing:
                memory.add("decision", entry, by="hive-import", time=f"{date}T00:00:00+00:00")
                decisions += 1
    if (repo / "handoffs").is_dir():
        for h in open_handoffs(repo / "handoffs"):
            entry = (f"Open Hive handoff '{h.title}' (handoffs/{h.file}), for {h.owner or 'any'}, "
                     f"status: {h.status}. {h.job}").strip()
            if entry not in existing:
                memory.add("note", entry, by="hive-import")
                handoffs += 1
    return decisions, handoffs
