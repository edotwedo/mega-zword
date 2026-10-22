"""No rule is added or changed without a passing ballot.

Phil, 2026-10-21: *"DO NOT ALLOW ANY RULE ADDITION OR CHANGES WITHOUT ANOTHER VOTE."* A rule saying
so would be worth nothing, so this is a hash: `approve` records the digest of the rules file only
after a ballot has passed, and `check` recomputes it. A test in the suite asserts `check`, and the
suite is the land-gate - so an unvoted rule change cannot be pushed.

Phil remains the owner: he can run `megazword rules approve <ballot>` himself, or bypass with
`MZ_SKIP_GATE=1`, and both are visible in the log rather than silent.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .filelock import write_atomic

REPO = Path(__file__).resolve().parents[2]
RULES_FILE = REPO / "docs" / "SYSTEM-DRAFT.md"


def hash_of(path: Path | None = None) -> str:
    target = path or RULES_FILE
    return hashlib.sha256(target.read_bytes()).hexdigest()


def approved_hash(path: Path | None = None) -> str:
    """The hash of the rules file AS COMMITTED ON origin/main.

    Hashing each worktree's copy made every seat that was behind main fail a test about a file it
    never touched - Quill-21 and Nock-21 both hit it on 2026-10-21 and could not land work. Comparing
    against main instead means a stale checkout passes and a genuinely unvoted change still fails,
    because it has to reach main to matter.
    """
    target = path or RULES_FILE
    try:
        shown = str(target.relative_to(REPO)).replace("\\", "/")
    except ValueError:
        return hash_of(target)  # a test path outside the repo has no main to ask
    proc = subprocess.run(["git", "show", f"origin/main:{shown}"], cwd=str(REPO),
                          capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        return hash_of(target)  # no origin/main yet (fresh clone), fall back to the file
    return hashlib.sha256(proc.stdout).hexdigest()


def approval_path(home: Path | None = None) -> Path:
    return (home or config.HOME) / "rules-approval.json"


def approval(home: Path | None = None) -> dict:
    try:
        return json.loads(approval_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def check(home: Path | None = None, path: Path | None = None) -> tuple[bool, str]:
    """(allowed, explanation). A missing approval means no unvoted rules exist yet - still a fail."""
    recorded = approval(home)
    if not recorded.get("sha256"):
        return False, ("the rules have no recorded ballot: run `megazword rules approve <ballot>` "
                       "after a vote, or the suite will keep failing")
    current = approved_hash(path)
    if current != recorded["sha256"]:
        return False, (f"the rules changed without a vote (approved {recorded['ballot']} at "
                       f"{recorded.get('approved', '?')}); hold a ballot and run "
                       f"`megazword rules approve <ballot>`")
    return True, f"rules approved by {recorded['ballot']} at {recorded.get('approved', '?')}"


def approve(ballot: str, *, home: Path | None = None, path: Path | None = None,
            messages=None, seats: list[str] | None = None) -> dict:
    """Record the hash, but only if that ballot actually passed."""
    from . import vote as vote_module
    if messages is None:
        from . import room
        messages = room.claim_messages("hive", config.load(), home)
    result = vote_module.tally(messages, ballot.upper(), seats=seats)
    if not result["reached"]:
        raise ValueError(f"{ballot.upper()} has not reached quorum ({len(result['cast'])} of "
                         f"{result['quorum']}) - no approval recorded")
    rejected = [item for item, counts in result["counts"].items() if counts["no"] >= counts["yes"]]
    if rejected:
        raise ValueError(f"{ballot.upper()} did not carry {', '.join(rejected)} - no approval recorded")
    if not result["cast"]:
        raise ValueError(f"{ballot.upper()} has no votes - no approval recorded")
    target = path or RULES_FILE
    try:
        shown = str(target.relative_to(REPO)).replace("\\", "/")
    except ValueError:
        shown = str(target)  # a test path outside the repo is still a legitimate target
    record = {"file": shown, "sha256": hash_of(path), "ballot": ballot.upper(),
              "approved": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "voters": sorted(vote["seat"] for vote in result["cast"].values())}
    path_out = approval_path(home)
    path_out.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path_out, json.dumps(record, indent=2) + "\n")
    return record


def command(args) -> int:
    action = getattr(args, "action", "check")
    if action == "approve":
        try:
            record = approve(args.ballot)
        except ValueError as exc:
            print(f"[megazword rules] {exc}")
            return 2
        print(f"recorded {record['ballot']} for {record['file']} by {', '.join(record['voters'])}")
        return 0
    allowed, message = check()
    print(("[megazword rules] " if not allowed else "[megazword rules] OK - ") + message)
    return 0 if allowed else 1


def add_parser(sub) -> None:
    parser = sub.add_parser("rules", help="no rule change lands without a passed ballot")
    parser.add_argument("action", nargs="?", default="check", choices=("check", "approve"))
    parser.add_argument("ballot", nargs="?", default="", help="proposal id that approved the rules")
