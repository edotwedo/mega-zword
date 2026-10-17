"""Team engine: combine a job's finished pieces into one reviewed branch.

`megazword job run` leaves each passed piece on its own `job/<ID>-<n>` branch.
`combine` merges them on `job/<ID>`, runs the full tests on the result, and has
reviewers from families that wrote none of the pieces check the combined diff.
Only `job/<ID>` is pushed; never main. Phil approves the branch himself.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from . import config, night
from .filelock import write_atomic

REVIEWERS = 2


def _family(name: str) -> str:
    return (name or "").split("-")[0]


def _load(job_id: str) -> tuple[Path, dict]:
    path = config.HOME / "jobs" / job_id / "job.json"
    if not path.exists():
        raise FileNotFoundError(f"no job {job_id} (looked for {path})")
    return path, json.loads(path.read_text(encoding="utf-8"))


def _retest(work: Path) -> tuple[str, str]:
    cmd, env = night.test_command(work, night.Job(0, " ", "", "combined job", "tests pass"))
    if not cmd:
        return "none", ""
    res = night.run_cmd(cmd, work, night.TEST_MINUTES * 60, env)
    tail = ((res.stdout or res.stderr or "").strip().splitlines() or [""])[-1]
    return ("passed" if res.returncode == 0 else "failed"), tail[:300]


def combine(job_id: str, backends: dict, cfg, review_fn=None, test_fn=None, push: bool = True) -> dict:
    """Merge passed pieces on job/<ID>, test, review; save and return `combined`."""
    from . import review
    path, report = _load(job_id)
    passed = [r for r in report.get("results", []) if r.get("status") == "passed" and r.get("branch")]
    branch = f"job/{job_id}"
    combined = {"branch": branch, "pieces": [r["index"] for r in passed], "status": "", "tests": "",
                "detail": "", "reviewers": [], "findings": []}

    def done(status: str, detail: str = "") -> dict:
        combined.update(status=status, detail=detail[:500])
        report["combined"] = combined
        write_atomic(path, json.dumps(report, indent=2))
        return combined

    if not passed:
        return done("nothing to combine", "no piece passed its tests")
    clone = Path(report["clone"])
    work = path.parent / "combined"
    night.git(["worktree", "remove", "--force", str(work)], clone)
    night._check(night.git(["worktree", "add", "--quiet", "-B", branch, str(work), report["base"]], clone),
                 "git worktree add")
    try:
        for row in passed:
            res = night.git(["merge", "--no-ff", "--quiet", "-m",
                             f"job {job_id}: combine piece {row['index']}", row["branch"]], work)
            if res.returncode != 0:
                night.git(["merge", "--abort"], work)
                return done("conflict", f"piece {row['index']} ({row.get('title', '')}) conflicts "
                                        "with the pieces before it")
        tests, tail = (test_fn or _retest)(work)
        combined["tests"] = tests
        if tests == "failed":
            return done("tests failed", tail)
        # Fresh eyes: reviewers from families that wrote none of the pieces.
        writers = {_family(r.get("ai", "")) for r in passed}
        others = {n: b for n, b in backends.items() if _family(n) not in writers}
        merged, raw, _ = (review_fn or review.collect)(work, others, cfg, base=report["base"],
                                                       count=REVIEWERS)
        combined["reviewers"] = sorted(raw)
        combined["findings"] = [asdict(f) for f in merged or []]
        if len(raw) < REVIEWERS:
            return done("needs review", f"got {len(raw)} of {REVIEWERS} reviews")
        stops = review.blocking(merged or [])
        if stops:
            return done("review found problems", "; ".join(f"{f.path}:{f.line} {f.text[:80]}" for f in stops[:3]))
        if not push:
            return done("ready")
        # Plain push only (never force): a branch left by an earlier combine stays as it was.
        res = night.git(["push", "--quiet", "origin", f"{branch}:refs/heads/{branch}"], work, 600)
        if res.returncode != 0:
            return done("ready, not pushed", f"{branch} already exists on origin; delete it there to push again")
        return done("ready", f"pushed {branch} for Phil to approve")
    finally:
        night.git(["worktree", "remove", "--force", str(work)], clone)


def format_combined(combined: dict) -> str:
    lines = [f"{combined['branch']}: {combined['status']}"
             + (f" ({combined['detail']})" if combined.get("detail") else "")]
    if combined.get("tests"):
        lines.append(f"  tests: {combined['tests']}")
    if combined.get("reviewers"):
        lines.append(f"  reviewed by: {', '.join(combined['reviewers'])}")
    for f in combined.get("findings", [])[:10]:
        agree = f" ({len(f['by'])} agree)" if len(f.get("by", [])) > 1 else ""
        lines.append(f"  [{f['severity']}] {f['path']}:{f['line']}{agree} - {f['text'][:120]}")
    return "\n".join(lines)
