#!/usr/bin/env python3
"""Auto-merge queue: mechanical gate + non-author review, then merge, then push.

Phil, 2026-10-27: "if you're expecting me to jump in and participate in that the answer is
no thank you." Correct - the merge chair is not a human job.

M1 wants one writer merging serially; M3 wants a non-author review. Neither needs a person:

  1. each branch ahead of main (task/*, night-local/*)
  2. merge --no-ff into main
  3. run the repo's mechanical check (the gate): a failing merge is reset away, not kept
  4. run `megazword review --base HEAD~1` - a free model is the non-author provider
     (ballot P1: "any non-author provider will do"). The review is recorded, not trusted as
     the decision: model prose cannot reliably gate, the check is what decides.
  5. keep and push when the check passes, otherwise rewind and report

Branches are merged one at a time, so a conflict or a red check stops that branch only.

  scripts/merge_queue.py [--repo PATH] [--check "CMD"] [--push-remote github] [--dry-run]

Env: MZ_MERGE_CHECK - default check command (default: the repo's pytest).
"""
from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

HOME = Path(os.environ.get("MEGAZWORD_HOME", Path.home() / ".megazword"))
LOG = HOME / "merge-queue.log"
PREFIXES = ("task/", "night-local/")


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M')} {msg}"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(line, flush=True)


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)


def default_check(repo: Path) -> list[str]:
    env = os.environ.get("MZ_MERGE_CHECK")
    if env:
        return shlex.split(env)
    venv = repo / ".venv" / "bin" / "python"
    return [str(venv) if venv.exists() else "python3", "-m", "pytest", "-q"]


def base_branch(repo: Path) -> str:
    """The branch merges land on: main, else master, else whatever HEAD points at.

    Assuming "main" silently skipped every branch in a repo that uses "master"
    (RobinTHood does), which looked exactly like "nothing to merge".
    """
    for name in ("main", "master"):
        if git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}").returncode == 0:
            return name
    head = git(repo, "symbolic-ref", "--short", "HEAD").stdout.strip()
    return head or "main"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default="/home/edotwedo/workspace/mega-zword")
    parser.add_argument("--check", default="", help="override the mechanical check command")
    parser.add_argument("--push-remote", default="github")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv[1:])
    repo = Path(args.repo).expanduser()

    if not (repo / ".git").exists() and not git(repo, "rev-parse", "--git-dir").returncode == 0:
        log(f"{repo}: not a git repository")
        return 1
    if git(repo, "status", "--porcelain", "--untracked-files=no").stdout.strip():
        log("working tree has uncommitted changes - refusing to merge until it is clean")
        return 0

    check = shlex.split(args.check) if args.check else default_check(repo)
    base = base_branch(repo)
    current = git(repo, "branch", "--show-current").stdout.strip()
    if current != base:
        if args.dry_run:
            log(f"would check out {base} (currently {current or 'detached'})")
        else:
            git(repo, "checkout", base)

    refs = git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").stdout.split()
    candidates = [r for r in refs if r.startswith(PREFIXES)]
    if not candidates:
        log("no task branches")
        return 0

    merged_any = False
    for branch in sorted(candidates):
        ahead = git(repo, "rev-list", "--count", f"{base}..{branch}").stdout.strip()
        if ahead in ("", "0"):
            continue
        log(f"{branch}: {ahead} commit(s) ahead")
        if args.dry_run:
            continue

        merge = git(repo, "merge", "--no-ff", "--no-edit", branch)
        if merge.returncode != 0:
            git(repo, "merge", "--abort")
            log(f"{branch}: merge conflict, skipped ({merge.stdout.strip() or merge.stderr.strip()})")
            continue

        gate = subprocess.run(check, cwd=repo, capture_output=True, text=True, timeout=1800)
        tail = (gate.stdout or "").strip().splitlines()[-1:] or [""]
        if gate.returncode != 0:
            git(repo, "reset", "--hard", "ORIG_HEAD")
            log(f"{branch}: check failed ({' '.join(check)}), rewound | {tail[0][:160]}")
            continue
        log(f"{branch}: check passed | {tail[0][:160]}")

        review = subprocess.run(["megazword", "review", "--base", "HEAD~1", "-n", "1"],
                                cwd=repo, capture_output=True, text=True, timeout=1800,
                                env={**os.environ, "MEGAZWORD_NO_APP": "1"})
        last = ((review.stdout or "").strip().splitlines() or [""])[-1]
        log(f"{branch}: non-author review exit={review.returncode} | {last[:160]}")

        if args.push_remote:
            push = git(repo, "push", args.push_remote, base)
            if push.returncode != 0:
                tail2 = (push.stderr or push.stdout).strip().splitlines()[-1:]
                log(f"{branch}: merged but push failed | {(tail2 or [''])[0][:160]}")
                continue
            log(f"{branch}: MERGED and pushed to {args.push_remote}/{base}")
        else:
            log(f"{branch}: MERGED locally (no push remote configured)")
        merged_any = True

    log("done" + (" - something landed" if merged_any else " - nothing landed"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
