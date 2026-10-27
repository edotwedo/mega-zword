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
  Its folder key drops a leading separator ('/home/me/proj' -> 'home-me-proj', where Claude
  keeps the dash), and it writes a ``<id>.checkpoints.jsonl`` beside each transcript
  (both verified on Linux, 2026-10-26).
- codex: date-partitioned rollout files; the first JSON line carries the cwd. Resume by id.
- agy: ``~/.gemini/antigravity-cli/conversations/<conversation-id>.db``, one global folder
  rather than a per-directory one. Resume: ``-c`` or ``--conversation <id>``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from pathlib import Path

from .claims import DESIGNATION

ROSTER = Path(__file__).resolve().parents[2] / "docs" / "HIVE-ROSTER.md"
CLAUDE_HOME = Path.home() / ".claude" / "projects"
CODECODE_HOME = Path.home() / ".commandcode" / "projects"
CODEX_SESSIONS = Path.home() / ".codex" / "sessions"
GROK_SESSIONS = Path.home() / ".grok" / "sessions"
AGY_CONVERSATIONS = Path.home() / ".gemini" / "antigravity-cli" / "conversations"

# The roster's "Worker" column, as the CLIs are actually named.
# Gemini's binary on this box is `agy` (Antigravity). Mapping the roster word to `gemini`
# made hive_resume.ps1 run a command that is not on PATH, so Forge-22's tab died with
# "command not found" - found by Harbor022's review of the first version, 2026-10-21.
WORKER_CLI = {
    "claude": "claude",
    "claude code": "claude",
    "codex": "codex",
    "grok": "grok",
    "gemini": "agy",
    "command code": "cmdc",
}

# A worker word naming a browser or cloud seat ("Claude (cloud)") is not a local CLI, so
# there is no tab on this machine to respawn. Skipping it is deliberate: the plan must not
# invent a worktree and a window for a seat that runs somewhere else.
REMOTE_WORKER = re.compile(r"\b(?:cloud|web)\b")
ROW = re.compile(rf"^\|\s*({DESIGNATION})\s*\|\s*([^|]+?)\s*\|", re.MULTILINE)

# CLIs that can be told "bring back the newest conversation". Four of them mean "the newest
# in THIS directory"; agy keeps one global folder instead. The first version of this list left
# agy out because Harbor022's audit found `resume` claiming a form it did not have (2026-10-21)
# - but that was the flag list being wrong, not agy lacking one: MIKE-54 supplied the real
# forms on 2026-10-26 (`agy -c`, `agy --conversation <id>`) and both are in the binary.
HAS_RECENT_FORM = ("claude", "grok", "codex", "cmdc", "agy")


def slug(path: str) -> str:
    """A directory path as the CLIs key their project folders: every non-alphanumeric
    character becomes '-'. 'C:\\Users\\mrmar' -> 'C--Users-mrmar'."""
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def seats(roster_text: str) -> list[tuple[str, str]]:
    """(designation, cli) for each seat on the roster, in file order.

    The Worker column is prose, so it is read loosely: a plain "Claude" and a
    "Claude (review)" both name the CLI, and only a cloud or browser seat is dropped -
    it has no local tab to respawn, which is a different thing from a row we failed to
    parse. The first version knew only the literal "Claude Code", so a roster whose
    Worker column said "Claude" lost the seat from the plan with nothing printed.
    """
    found = []
    seen = set()
    for designation, worker in ROW.findall(roster_text):
        word = worker.strip().casefold()
        if REMOTE_WORKER.search(word):
            continue
        cli = WORKER_CLI.get(word) or WORKER_CLI.get(re.sub(r"\s*\([^)]*\)", "", word).strip())
        # The roster carries the Windows team and the Linux team in separate tables, and one
        # designation must never appear twice in the plan: the launcher would open two windows
        # for it. First row wins.
        if cli and designation.casefold() not in seen:
            found.append((designation, cli))
            seen.add(designation.casefold())
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


def cmdc_slug(directory: str) -> str:
    """Command Code's project folder for a directory: like ``slug``, lowercased, but with a
    leading separator dropped. Verified on Linux, 2026-10-26: this directory is filed as
    ``home-edotwedo-workspace-mega-zword``, where Claude files the same one as
    ``-home-edotwedo-workspace-mega-zword``. Keeping the dash is right for Claude and wrong
    here, and it made every cmdc seat report "no session" on this machine."""
    return slug(directory).lower().removeprefix("-")


def cmdc_session(directory: str, home: Path | None = None) -> str | None:
    """Command Code scopes sessions to the project directory, so the newest transcript
    there is the one to continue.

    ``<id>.checkpoints.jsonl`` sits beside ``<id>.jsonl`` and is a .jsonl too, so choosing
    the newest file by mtime alone could hand back ``<id>.checkpoints`` as a session id -
    and while a seat is working it is routinely the newer of the two.
    """
    root = home or CODECODE_HOME
    newest: tuple[float, str] | None = None
    # Both spellings are tried: the fix above is measured, and a CLI that changes its folder
    # key again should degrade to the old guess rather than to nothing.
    for name in dict.fromkeys((cmdc_slug(directory), slug(directory).lower())):
        try:
            found = [(path.stat().st_mtime, path.stem)
                     for path in (root / name).glob("*.jsonl")
                     if path.is_file() and not path.name.endswith(".checkpoints.jsonl")]
        except OSError:
            continue
        for entry in found:
            if newest is None or entry[0] > newest[0]:
                newest = entry
    return newest[1] if newest else None


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


def resume_args(cli: str, directory: str, session: str | None, fresh: bool = False) -> list[str]:
    """The flags that bring this seat's conversation back.

    When the exact session cannot be named, every one of these CLIs has a "most recent"
    form - claude `-c`, codex `resume --last`, grok `-c`, cmdc `-c`, agy `-c`. For all but agy
    that means the newest conversation in THIS directory, which is what a respawn means: it is
    strictly better than starting a stranger, because the directory is the seat's, so the
    newest conversation in it is almost certainly the right one. ``fresh`` asks for none of it.
    """
    base = ["--permission-mode", "acceptEdits"] if cli in ("claude", "grok") else []
    if fresh:
        return base
    if cli in ("claude", "grok"):
        return base + (["--resume", session] if session else ["-c"])
    if cli == "codex":
        return ["resume", session] if session else ["resume", "--last"]
    if cli == "cmdc":
        return ["-r", session] if session else ["-c"]
    if cli == "agy":
        # MIKE-54, 2026-10-26: `agy -c` continues the newest conversation and
        # `agy --conversation <id>` targets one exactly. Both are in the binary.
        return ["--conversation", session] if session else ["-c"]
    return base


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


def grok_session(directory: str, home: Path | None = None) -> str | None:
    """Grok keys sessions by the URL-encoded working directory, then by session id:
    ~/.grok/sessions/<quoted-cwd>/<session-id>/chat_history.jsonl."""
    folder = (home or GROK_SESSIONS) / urllib.parse.quote(directory, safe="")
    try:
        sessions = [d for d in folder.iterdir() if d.is_dir()]
    except OSError:
        return None
    best: tuple[float, str] | None = None
    for session in sessions:
        history = session / "chat_history.jsonl"
        if not history.is_file():
            continue
        stamp = history.stat().st_mtime
        if best is None or stamp > best[0]:
            best = (stamp, session.name)
    return best[1] if best else None


def agy_session(directory: str, home: Path | None = None) -> str | None:
    """Antigravity (agy) keeps one ``<conversation-id>.db`` per conversation in a single global
    folder - not under a directory slug like the others, so the newest file is the newest
    conversation. ``directory`` is accepted for the caller's uniform signature and ignored.
    """
    folder = home or AGY_CONVERSATIONS
    try:
        files = [path for path in folder.glob("*.db") if path.is_file()]
    except OSError:
        return None
    if not files:
        return None
    return max(files, key=lambda path: path.stat().st_mtime).stem


def find_session(cli: str, directory: str, designation: str = "") -> str | None:
    if cli == "claude":
        return claude_session_for(designation, directory) if designation else claude_session(directory)
    if cli == "cmdc":
        return cmdc_session(directory)
    if cli == "grok":
        return grok_session(directory)
    if cli == "codex":
        return codex_session(directory)
    if cli == "agy":
        return agy_session(directory)
    return None


def registry_path(home: Path | None = None) -> Path:
    from . import config
    return (home or config.HOME) / "hive_seats.json"


def read_recorded(home: Path | None = None) -> dict:
    """What we know about how each seat was last launched, keyed by lowercased name."""
    try:
        data = json.loads(registry_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def record(entries: list[dict], home: Path | None = None) -> None:
    """Remember how each seat was launched, so the NEXT respawn is exact.

    Nothing recorded this before 2026-10-20, which is the whole reason respawn never
    worked: a seat that ran from the shared repo or from home is indistinguishable from
    any other, and two seats fall out of the same directory. Recording at launch is the
    only thing that turns this from a guess into a fact.
    """
    known = read_recorded(home)
    for entry in entries:
        known[entry["designation"].lower()] = {
            "designation": entry["designation"],
            "cli": entry["cli"],
            "dir": entry["dir"],
        }
    path = registry_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(known, indent=2, sort_keys=True), encoding="utf-8")


def plan(roster_text: str, seats_root: Path, fallback_dir: Path,
         home: Path | None = None) -> list[dict]:
    """One entry per seat: who it is, where it lives, and how to resume it.

    A recorded launch beats a guess about the directory; the roster is only the fallback
    for a seat we have never seen launched.
    """
    entries = []
    recorded = read_recorded(home)
    for designation, cli in seats(roster_text):
        remembered = recorded.get(designation.lower(), {})
        dirname = remembered.get("dir", "")
        candidate = Path(dirname) if dirname else seats_root / designation.lower()
        if not candidate.is_dir():
            candidate = seats_root / designation.lower()
        directory = candidate if candidate.is_dir() else fallback_dir
        session = find_session(remembered.get("cli") or cli, str(directory), designation)
        entries.append({
            "designation": designation,
            "cli": remembered.get("cli") or cli,
            "dir": str(directory),
            "session": session or "",
            "args": resume_args(remembered.get("cli") or cli, str(directory), session),
        })
    return entries


def command(args) -> int:
    if getattr(args, "record_stdin", False):
        # The launchers know what they launched before any roster or session exists, so let
        # them hand it over as JSON rather than re-deriving it. PowerShell collapses a
        # one-element array to a bare object, so accept both shapes.
        try:
            payload = json.loads(sys.stdin.read() or "[]")
        except ValueError:
            return 1
        entries = [payload] if isinstance(payload, dict) else payload
        if isinstance(entries, list):
            record([e for e in entries if isinstance(e, dict) and e.get("designation")])
        return 0
    roster = Path(args.roster).read_text(encoding="utf-8")
    entries = plan(roster, Path(args.seats), Path(args.fallback))
    if getattr(args, "fresh", False):
        for entry in entries:
            entry["session"] = ""
            entry["args"] = resume_args(entry["cli"], entry["dir"], None, fresh=True)
    if getattr(args, "record", False):
        record(entries)
    if args.json:
        print(json.dumps(entries, indent=2))
        return 0
    for entry in entries:
        if entry["session"]:
            where = entry["session"]
        elif getattr(args, "fresh", False):
            where = "(fresh start; nothing resumed)"
        elif entry["cli"] not in HAS_RECENT_FORM:
            where = "starts fresh (this CLI has no resume-the-newest form)"
        else:
            where = "continues the newest session in that directory"
        print(f"{entry['designation']:<12} {entry['cli']:<7} {entry['dir']}")
        print(f"{'':12} resume: {where}")
    return 0


def add_parser(sub) -> None:
    resume = sub.add_parser("resume", help="respawn each seat with its name")
    resume.add_argument("--json", action="store_true", help="machine-readable plan for the launcher")
    resume.add_argument("--fresh", action="store_true",
                        help="start new conversations instead of resuming the last one")
    resume.add_argument("--record", action="store_true",
                        help="save how each seat was launched, so the next respawn is exact")
    resume.add_argument("--record-stdin", action="store_true",
                        help="internal: read a JSON list of launched seats from stdin and record it")
    resume.add_argument("--roster", default=str(ROSTER), help="roster file to read")
    resume.add_argument("--seats", default=str(Path.home() / "mz-seats"), help="seat worktree root")
    resume.add_argument("--fallback", default=str(Path.home() / "mega-zword"),
                        help="directory to use when a seat has no worktree of its own")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--record-stdin", action="store_true")
    parser.add_argument("--roster", default=str(ROSTER))
    parser.add_argument("--seats", default=str(Path.home() / "mz-seats"))
    parser.add_argument("--fallback", default=str(Path.home() / "mega-zword"))
    return command(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
