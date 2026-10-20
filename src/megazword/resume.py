"""Respawn a seat: same designation, same conversation.

Phil, 2026-10-20: "the point of the respawn was to RESPAWN - resume everything and retain
the seat."

Neither existing script did that. `hive_up.ps1` brings the floor up as one tab per CLI with
a generic lane name, no MEGAZWORD_SEAT and no conversation. `hive-resume.ps1` restores
conversations but is a hand-written list of four sessions from 14 Oct and never sets the
seat. This module supplies the missing half: for each seat on the roster, find its
directory and its most recent session so the launcher can resume the right conversation
UNDER THE RIGHT NAME.

Session stores, as they actually are on this machine (verified, not assumed):
- claude: ``~/.claude/projects/<slug>/<session-id>.jsonl`` where the slug is the directory
  path with every non-alphanumeric character turned into ``-``. Resume: ``--resume <id>``.
- cmdc: sessions are project-scoped, ``~/.commandcode/projects/<slug>/``. Resume: ``-c``.
- codex: date-partitioned rollout files; the first JSON line carries the cwd. Resume by id.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROSTER = Path(__file__).resolve().parents[2] / "docs" / "HIVE-ROSTER.md"
CLAUDE_HOME = Path.home() / ".claude" / "projects"
CODECODE_HOME = Path.home() / ".commandcode" / "projects"
CODEX_SESSIONS = Path.home() / ".codex" / "sessions"

# The roster's "Worker" column, as the CLIs are actually named.
WORKER_CLI = {
    "claude code": "claude",
    "codex": "codex",
    "grok": "grok",
    "command code": "cmdc",
}
ROW = re.compile(r"^\|\s*([A-Za-z]+-\d+)\s*\|\s*([^|]+?)\s*\|", re.MULTILINE)


def slug(path: str) -> str:
    """A directory path as the CLIs key their project folders: every non-alphanumeric
    character becomes '-'. 'C:\\Users\\mrmar' -> 'C--Users-mrmar'."""
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def seats(roster_text: str) -> list[tuple[str, str]]:
    """(designation, cli) for each seat on the roster, in file order."""
    found = []
    for designation, worker in ROW.findall(roster_text):
        cli = WORKER_CLI.get(worker.strip().casefold())
        if cli:
            found.append((designation, cli))
    return found


def claude_session(directory: str, home: Path | None = None) -> str | None:
    """The newest conversation id for this directory, or None."""
    folder = (home or CLAUDE_HOME) / slug(directory)
    try:
        files = [f for f in folder.glob("*.jsonl") if f.is_file()]
    except OSError:
        return None
    if not files:
        return None
    return max(files, key=lambda f: f.stat().st_mtime).stem


def cmdc_session(directory: str, home: Path | None = None) -> str | None:
    """Command Code scopes sessions to the project directory, so the newest transcript
    there is the one to continue."""
    folder = (home or CODECODE_HOME) / slug(directory).lower()
    try:
        files = [f for f in folder.glob("*.jsonl") if f.is_file()]
    except OSError:
        return None
    if not files:
        return None
    return max(files, key=lambda f: f.stat().st_mtime).stem


def codex_session(directory: str, home: Path | None = None) -> str | None:
    """Codex rolls sessions into date folders and the filename carries the id, but only
    the record inside knows which directory the session ran in - so read the first line."""
    root = home or CODEX_SESSIONS
    want = str(Path(directory)).lower()
    best: tuple[float, str] | None = None
    try:
        candidates = list(root.rglob("rollout-*.jsonl"))
    except OSError:
        return None
    for path in candidates:
        try:
            with path.open(encoding="utf-8") as handle:
                first = handle.readline()
            record = json.loads(first)
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        if str(record.get("cwd", "")).lower() != want:
            continue
        stamp = path.stat().st_mtime
        if best is None or stamp > best[0]:
            best = (stamp, _codex_id(path))
    return best[1] if best else None


def _codex_id(path: Path) -> str:
    """rollout-2026-10-20T14-21-16-<uuid>.jsonl -> <uuid>"""
    match = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
                      path.stem)
    return match.group(1) if match else path.stem


def resume_args(cli: str, directory: str, session: str | None) -> list[str]:
    """The flags that bring this seat's conversation back, or a fresh start if unknown."""
    if cli == "claude":
        return ["--permission-mode", "acceptEdits", "--resume", session] if session else ["--permission-mode", "acceptEdits"]
    if cli == "grok":
        return ["--permission-mode", "acceptEdits", "--resume", session] if session else ["--permission-mode", "acceptEdits"]
    if cli == "codex":
        return ["resume", session] if session else []
    if cli == "cmdc":
        return ["-r", session] if session else ["-c"]
    return []


def claude_session_for(designation: str, directory: str, home: Path | None = None) -> str | None:
    """Claude's newest session FOR THIS SEAT.

    The project folder is keyed on the directory Claude ran in, and a seat does not always
    run in the worktree named after it - on 2026-10-20 Beacon-17's worktree existed but its
    transcript did not, because Claude had been started elsewhere. So look at the seat's own
    directory first, then at any project folder that names the seat.
    """
    direct = claude_session(directory, home)
    if direct:
        return direct
    root = home or CLAUDE_HOME
    try:
        folders = [f for f in root.iterdir() if f.is_dir() and designation.lower() in f.name.lower()]
    except OSError:
        return None
    best: tuple[float, str] | None = None
    for folder in folders:
        try:
            files = [f for f in folder.glob("*.jsonl") if f.is_file()]
        except OSError:
            continue
        for path in files:
            stamp = path.stat().st_mtime
            if best is None or stamp > best[0]:
                best = (stamp, path.stem)
    return best[1] if best else None


def find_session(cli: str, directory: str, designation: str = "") -> str | None:
    if cli == "claude":
        return claude_session_for(designation, directory) if designation else claude_session(directory)
    if cli == "cmdc":
        return cmdc_session(directory)
    if cli == "codex":
        return codex_session(directory)
    return None


def plan(roster_text: str, seats_root: Path, fallback_dir: Path) -> list[dict]:
    """One entry per seat: who it is, where it lives, and how to resume it."""
    entries = []
    for designation, cli in seats(roster_text):
        candidate = seats_root / designation.lower()
        directory = candidate if candidate.is_dir() else fallback_dir
        session = find_session(cli, str(directory), designation)
        entries.append({
            "designation": designation,
            "cli": cli,
            "dir": str(directory),
            "session": session or "",
            "args": resume_args(cli, str(directory), session),
        })
    return entries


def command(args) -> int:
    roster = Path(args.roster).read_text(encoding="utf-8")
    entries = plan(roster, Path(args.seats), Path(args.fallback))
    if getattr(args, "fresh", False):
        for entry in entries:
            entry["session"] = ""
            entry["args"] = resume_args(entry["cli"], entry["dir"], None)
    if args.json:
        print(json.dumps(entries, indent=2))
        return 0
    for entry in entries:
        if entry["session"]:
            where = entry["session"]
        elif entry["cli"] == "cmdc":
            # Command Code scopes sessions to the project directory, so -c continues the
            # right one without knowing its id. Saying "starts fresh" here would be a lie.
            where = "-c (continues the newest session in that directory)"
        else:
            where = "(no session found; starts fresh)"
        print(f"{entry['designation']:<12} {entry['cli']:<7} {entry['dir']}")
        print(f"{'':12} resume: {where}")
    return 0


def add_parser(sub) -> None:
    resume = sub.add_parser("resume", help="respawn each seat with its name")
    resume.add_argument("--json", action="store_true", help="machine-readable plan for the launcher")
    resume.add_argument("--fresh", action="store_true",
                        help="start new conversations instead of resuming the last one")
    resume.add_argument("--roster", default=str(ROSTER), help="roster file to read")
    resume.add_argument("--seats", default=str(Path.home() / "mz-seats"), help="seat worktree root")
    resume.add_argument("--fallback", default=str(Path.home() / "mega-zword"),
                        help="directory to use when a seat has no worktree of its own")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--roster", default=str(ROSTER))
    parser.add_argument("--seats", default=str(Path.home() / "mz-seats"))
    parser.add_argument("--fallback", default=str(Path.home() / "mega-zword"))
    return command(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
