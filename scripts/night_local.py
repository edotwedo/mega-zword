#!/usr/bin/env python3
"""Local overnight driver for the Linux port.

Why this exists: ``megazword night`` clones a GitHub repo, so its ``night/<date>``
branches fork off main and miss the seats' local work. docs/ROADMAP.md #3 wants
Night Shift on **local Gitea**, and Gitea (127.0.0.1:3000) is down. This driver is
tonight's stopgap: it runs the port's waiting jobs in THIS working tree, one job per
invocation, and leaves the changes uncommitted for morning review.

Safety: one job per tick (the timer's oneshot keeps ticks from overlapping); the
STOP file pauses it; each job is tried on codex -> claude -> gemini (all 'free' per
the guard) and only the first backend that actually changes the tree counts. cmdc is
throttled and grok is hard-only, so neither is used.
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

HOME = Path(os.environ.get("MEGAZWORD_HOME", Path.home() / ".megazword"))
REPO = Path(os.environ.get("MZ_NIGHT_REPO", "/home/edotwedo/workspace/mega-zword"))
JOBS = HOME / "night" / os.environ.get("MZ_NIGHT_JOBS", "local-jobs.json")
STATE = HOME / "night" / os.environ.get("MZ_NIGHT_STATE", "local-state.json")
LOG = HOME / "night" / os.environ.get("MZ_NIGHT_LOG", "local.log")
STOP = HOME / "STOP"
BACKENDS = ("codex", "claude", "gemini")
# A reviewer reads the diff; only a compiler proves it. Set MZ_NIGHT_CHECK to the repo's own
# mechanical gate (RobinTHood: `npx --no-install tsc --noEmit`) and a job that changes code but
# fails it is not done, whatever the model or the reviewer said.
CHECK = os.environ.get("MZ_NIGHT_CHECK", "")
CHECK_TIMEOUT = 600
JOB_TIMEOUT = 1500  # seconds
MAX_ATTEMPTS = 2


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M')} {msg}"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(line, flush=True)


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def tree_digest() -> str:
    """Content hash of the working tree, so a change shows even when the tree is already dirty.

    Porcelain status alone is not enough: a backend editing a file that was already modified
    leaves the same 'M path' line, so the first job reported 'no change' while codex and gemini
    were in fact editing the file. Hash the diff content instead.
    """
    diff = subprocess.run(["git", "diff", "HEAD"], cwd=REPO,
                          capture_output=True, text=True).stdout
    untracked = subprocess.run(["git", "status", "--porcelain"], cwd=REPO,
                               capture_output=True, text=True).stdout
    return hashlib.sha256((diff + untracked).encode("utf-8", "replace")).hexdigest()


def run_one(backend: str, prompt: str) -> bool:
    """Run the job on one backend. True if the tree changed (i.e. it did something)."""
    before = tree_digest()
    try:
        completed = subprocess.run(
            ["megazword", "run", "--edit", "-m", backend, prompt],
            cwd=REPO, capture_output=True, text=True, timeout=JOB_TIMEOUT,
            env={**os.environ, "MEGAZWORD_NO_APP": "1"},
        )
    except subprocess.TimeoutExpired:
        log(f"  {backend}: timed out after {JOB_TIMEOUT}s")
        return False
    changed = tree_digest() != before
    tail = (completed.stdout or "").strip().splitlines()[-1:] or [""]
    log(f"  {backend}: exit={completed.returncode} changed={changed} | {tail[0][:120]}")
    if changed and CHECK:
        check = subprocess.run(shlex.split(CHECK), cwd=REPO, capture_output=True,
                               text=True, timeout=CHECK_TIMEOUT)
        first = (check.stderr or check.stdout or "").strip().splitlines()[:2]
        log(f"  check: exit={check.returncode} ({CHECK}) {' | '.join(first)[:160]}")
        if check.returncode != 0:
            return False
    return changed


def commit_and_review(jid: str, files: list[str]) -> None:
    """M3: commit the job, then hand it to a non-author reviewer before it can land.

    ``megazword review`` reads commits between ``--base`` and HEAD, not the working tree, so
    the change has to be committed first for any review to happen at all.
    """
    subprocess.run(["git", "add", "--", *files], cwd=REPO, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-q", "-m", f"night_local {jid}"], cwd=REPO,
                   capture_output=True, text=True)
    review = subprocess.run(["megazword", "review", "--base", "HEAD~1", "-n", "1"],
                            cwd=REPO, capture_output=True, text=True, timeout=JOB_TIMEOUT,
                            env={**os.environ, "MEGAZWORD_NO_APP": "1"})
    last = ((review.stdout or "").strip().splitlines() or [""])[-1]
    log(f"  review: exit={review.returncode} | {last[:160]}")


def main() -> int:
    if STOP.exists():
        log("stopped: STOP file is set")
        return 0
    # Work on whatever branch is checked out: main. There is ONE branch now - the newest commit
    # on main is "the fixed one" (Phil, 2026-10-27). Per-job branches bought us wrong-branch
    # commits, orphaned commits and merge conflicts for no benefit, so they are gone.
    spec = load(JOBS, {})
    jobs = spec.get("jobs", []) if isinstance(spec, dict) else []
    if not jobs:
        log("queue clear: no local jobs")
        return 0
    state = load(STATE, {})
    for job in jobs:
        jid = job.get("id")
        if state.get(jid, {}).get("state") in ("done", "failed"):
            continue
        attempts = state.get(jid, {}).get("attempts", 0)
        log(f"job {jid} (attempt {attempts + 1})")
        for backend in BACKENDS:
            if run_one(backend, job["prompt"]):
                state[jid] = {"state": "done", "backend": backend,
                              "at": time.strftime("%Y-%m-%dT%H:%M")}
                save(STATE, state)
                commit_and_review(jid, job.get("files", []))
                log(f"job {jid} done on {backend}")
                return 0
        attempts += 1
        state[jid] = {"state": "failed" if attempts >= MAX_ATTEMPTS else "waiting",
                      "attempts": attempts, "at": time.strftime("%Y-%m-%dT%H:%M")}
        save(STATE, state)
        log(f"job {jid}: no backend changed the tree (attempt {attempts})")
        return 0
    log("queue clear: every local job is done or failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
