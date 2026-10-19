"""What one job cost, per model: steps and tokens, straight from the run log.

`job status` shows a saved job's pieces and `job scores` ranks AIs across every
job ever run, so neither answers "what did THIS job spend, and on which model".
The run log already holds it: job_workers appends one line per attempt carrying
project=<job id>, the backend that ran it, its request (step) count and its
estimated tokens.

The number is honest about what it is: est_tokens is Mega Zword's own
(prompt_chars + answer_chars) // 4 estimate, the same one the usage table shows,
not billed tokens or money. This is a readout, never a guess dressed as a bill.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from . import config, job, runlog

TOKEN_NOTE = "est_tokens is (prompt + answer chars) // 4, not billed tokens"


def entries_for(job_id: str, log_path: Path | None = None) -> list[dict]:
    """Run-log entries belonging to this job. Other projects are ignored."""
    path = log_path or config.HOME / "log.jsonl"
    return [e for e in runlog.read(path) if str(e.get("project") or "") == job_id]


def by_model(entries: list[dict]) -> list[dict]:
    """Per backend: steps (model requests), runs, ok count and estimated tokens.
    Most tokens first, so the expensive model is the first line read."""
    stats: dict[str, dict] = {}
    for entry in entries:
        name = str(entry.get("backend") or "?")
        row = stats.setdefault(name, {"ai": name, "steps": 0, "runs": 0, "ok": 0, "est_tokens": 0})
        row["runs"] += 1
        row["ok"] += 1 if entry.get("ok") else 0
        row["steps"] += max(1, int(entry.get("requests") or 1))
        row["est_tokens"] += int(entry.get("est_tokens") or 0)
    return sorted(stats.values(), key=lambda r: (-r["est_tokens"], r["ai"]))


def format_cost(job_id: str, rows: list[dict]) -> str:
    if not rows:
        return (f"job {job_id}: nothing in the run log for it "
                "(it has not run, or the log has rolled past it)")
    steps = sum(r["steps"] for r in rows)
    tokens = sum(r["est_tokens"] for r in rows)
    runs = sum(r["runs"] for r in rows)
    width = max(len(r["ai"]) for r in rows)
    lines = [f"job {job_id}: {steps} steps in {runs} attempts over {len(rows)} model(s), "
             f"{tokens:,} est_tokens",
             f"{'AI':<{width}}  steps  runs  ok  est_tokens"]
    lines += [f"{r['ai']:<{width}}  {r['steps']:>5}  {r['runs']:>4}  {r['ok']:>2}  {r['est_tokens']:>10,}"
              for r in rows]
    lines.append(TOKEN_NOTE)
    return "\n".join(lines)


def cost_job(job_id: str, log_path: Path | None = None,
             write: Callable[[str], None] = print) -> int:
    """`megazword job cost ID`: read the saved job and its log lines; run nothing."""
    if not (job.jobs_home() / job_id / "job.json").is_file():
        write(f"job cost: no job {job_id} (make one with `megazword job plan`)")
        return 1
    write(format_cost(job_id, by_model(entries_for(job_id, log_path))))
    return 0
