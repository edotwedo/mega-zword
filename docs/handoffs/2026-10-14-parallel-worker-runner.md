# Parallel worker runner — Sorrel-12 assignment

- **For:** Lantern-13, implementation; Quill-12, review/integration
- **Status:** done 2026-10-14 by Lantern-13; ready for Quill-12 review/integration
- **Source:** Q comment 6169667419 from Sorrel-12. Part 1 planner is owned by Night Shift.
- **Branch:** codex/parallel-workers-2026-10-14

## Done when
The worker runner executes hand-written independent plans in separate worktrees,
routes easy pieces through the existing free coding loop with failover, and owns
git/tests/commits. Fake-backend/local-bare-repo tests pass. No planner duplication.

## Integration contract
`job_workers.run_pieces(plan, repo, job_id=None, workers=..., cfg=..., backends=...)`.
Plan is a dict with `pieces`, each containing title, files, difficulty and test.
Planner validation/overlap merging remains part 1; the runner also rejects overlaps
before starting any worker. Results persist under HOME/jobs/ID/job.json.

## Report
Implemented `src/megazword/job_workers.py`. `run_pieces` accepts the saved planner
JSON dict and a repo path/owner-name, plus worker count and optional ID/config/backends.
It preserves planner attribution and ID, makes one isolated clone, and launches each
piece in `HOME/jobs/ID/piece-N`, branch `job/ID-N`. All pieces start at the same base.
Overlapping or private paths are refused before any worker starts; no duplicate
workers for an active or finished ID. Reusing an ID for a different plan is refused.

Easy pieces run the existing free coding loop, with provider pacing and in-loop
failover. An unsuccessful easy loop can receive one paid retry; paid capacity is
rechecked immediately before it starts, and the failed attempt's edits are discarded.
Paid CLI workers are reserved so simultaneous pieces use different seats. Medium/hard
pieces require a fresh usage meter and at least 15% left. No worker means a skipped
result, not fabricated completion.

Mega Zword stages and checks exact allowed files, rejects secret-looking changes and
weak Python tests, commits, runs the configured tests with Night Shift's stripped
environment, and refuses delivery if a worker/test changes HEAD, branch or tracked
files. Results include AI, attempted backends, elapsed seconds, tests, commit/branch,
request count and rough token estimate. Normal run logging includes free failover
attribution. Successful branches remain in the clone named in job.json. No main
changes, no push, no combine: final review/combine/push belong to the next stage.
Planner-supplied test commands are restricted to pytest and npm test/typecheck; shell
operators and arbitrary Python/shell commands are refused.

Also fixed two validation issues found while exercising this path: fake CLIs now use
UTF-8 on stdin/stdout/stderr (three existing tab-session tests failed on cp1252), and
agent call timeouts never exceed wall_timeout due to float rounding. Ollama coding
calls now preserve chat roles through /api/chat; regular generation keeps /api/generate.

Validation:
- Full suite: `python -m pytest -q` -> 1030 passed in 143.70 seconds.
- Final runner suite after metadata/Unicode scope refinement:
  `python -m pytest -q tests/test_job_workers.py` -> 12 passed in 37.11 seconds.
- Agent/Ollama/tab-session focused suite -> 125 passed.
- `scripts/smoke.py` -> 36/36; clean `git diff --check`.
- All automated tests use scripted models and local bare git repos: no API/paid calls.
- Actual local `qwen2.5-coder:7b` is now installed. Bounded live runner trials failed
  with a step cap or no edits. The runner refused a commit and did not escalate to
  paid AI in those local-only probes. These are failure-handling proofs, not successful
  real-model coding proofs. Proof records remain in local Temp mz-worker-* folders.

Next for Quill-12: merge/review this component alongside plan-only PR 44, then wire
the job run command to load job.json and call run_pieces with its ID. Add the separate
combined-review/merge/push stage; passing piece refs are in report['clone'].
Do not merge `codex/night-free-workers-2026-10-14`: that earlier integration was
shelved when Phil directed this chat to follow Sorrel-12's part 2 assignment.
