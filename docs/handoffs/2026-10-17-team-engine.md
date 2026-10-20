# Team engine (ROADMAP item 5)

**Status:** open. Written by Juniper-16 (Claude Code), 2026-10-17. Worked one step per
heartbeat beat by free models; Juniper-16 takes the steps marked (Juniper-16) and fixes
what the free models get wrong. Claim a step by writing `(taken: NAME, date)` after it.

## Goal
Phil gives one bigger coding job. Mega Zword splits it, several models work on the pieces
at the same time, tests decide, a different family reviews, and Phil gets one combined
branch to approve. A scoreboard shows who is good at what and what it cost.

## What already exists (don't rebuild it)
- `megazword job plan "TEXT"` (src/megazword/job.py): one AI splits the job into pieces
  (title, files, difficulty, test) and saves `~/.megazword/jobs/<ID>/job.json`.
- `job_workers.run_pieces(plan, repo, workers=N)` (src/megazword/job_workers.py): clones
  the repo, gives each piece its own worktree and branch `job/<ID>-<n>`, free models first
  then one paid retry, refuses edits outside the piece's files, runs the piece's test,
  commits, and writes results into the same job.json. It never merges or pushes.
- `review.collect(...)` (src/megazword/review.py): free reviewers from different families.

## Rules for every step
- One step per change. Code in src/megazword/job.py, job_workers.py, or a new
  src/megazword/team.py; tests in tests/test_team.py (new) or tests/test_job*.py.
- Tests use fakes and tmp_path; no network, no real AI, no real Gitea.
- Pure functions for formatting and scoring (take dicts, return text or dicts).
- Never push to main from a job; job branches only.
- Don't edit routing.py, ledger.py, budget.py, heartbeat.py or night.py.

## Steps (do the first one not yet done; tick it here with date and commit)
1. [x] (2026-10-17, heartbeat/openrouter + Juniper-16; job.run_job, tests/test_job_run.py) `megazword job run ID [--workers N] [--repo URL]`: load
   `~/.megazword/jobs/ID/job.json`, call `job_workers.run_pieces(plan, repo, job_id=ID,
   workers=N)`, then print one line per piece: number, title, status, AI, reason. Default
   repo: the local Gitea mega-zword URL (`heartbeat.GITEA`). Missing job: a clear message
   and exit code 1. Tests monkeypatch `run_pieces`.
2. [x] (2026-10-18, Juniper-16; job.format_status, job.status_job) `megazword job status ID`: a pure `format_status(report) -> str` showing the overall
   `runner_status`, then per piece: number, title, status, tests, AI that delivered, AIs
   tried, branch, reason. Works on a plan that hasn't run yet ("not started"). Tests with
   small dict fixtures.
3. [x] (2026-10-18, Juniper-16; job.parse_plan, Runner.brief, BRIEF_CHARS 1500) Shared brief: `planner_prompt` asks for
   `{"brief": "...", "pieces": [...]}`; `parse_pieces` keeps accepting a bare list (old
   plans). Save `brief` in job.json. In `Runner.run_piece`, when the plan has a brief, the
   worker prompt starts with "Shared brief for every worker on this job: ...". Tests: both
   plan shapes parse; the prompt includes the brief.
4. [x] (2026-10-17, Juniper-16; job_workers.free_attempts, HARD_ATTEMPTS) Several attempts on hard pieces: a hard piece that fails gets up to 3
   free attempts, each from a different family (by name prefix: groq-*, openrouter-*,
   tencent-*, zai-*, nvidia-*, gemini-api*, cheap-*), before the paid retry. Keep the first
   attempt that passes its test. Record every attempt in `result.tried`.
5. [x] (2026-10-17, Juniper-16; src/megazword/team.py, tests/test_team.py) `megazword job combine ID`: in the job's clone, branch `job/ID` from
   the base, merge every passed piece branch, run the full test command, then send the
   combined diff to `review.collect` with 2 reviewers from families that didn't write any
   piece. Save `combined` (branch, tests, review findings) in job.json and push `job/ID`
   to origin. Never main. A merge conflict or failing tests stops and is recorded.
6. [x] (2026-10-18, free model zai-47 drafted, Juniper-16 rewrote; src/megazword/scores.py) Scoreboard: pure `scoreboard(reports) -> list[dict]` over every
   `~/.megazword/jobs/*/job.json`: per AI, pieces delivered, pieces failed, pass rate,
   estimated tokens; plus `megazword job scores` printing it best first. Tests with
   fixtures.
7. [x] docs/GUIDE.md "Team jobs" section (started by Juniper-16 with plan and combine; run by zai via `megazword run`, status by Juniper-16, 2026-10-18; scores still to add after step 6):
   add run, status and scores once they exist, in the same plain style, with one
   example. Check every command against `megazword job --help`.
8. [phil] First real job on another project (e.g. Up Dawg), chosen by Phil.

## Done when
A job planned with `megazword job plan` runs, combines into one reviewed `job/ID` branch,
and `megazword job scores` shows who did what; step 8 then finishes ROADMAP item 5.

## Heartbeat log
- 2026-10-17: step 1 done. The 16:30 beat's free model (openrouter) wrote `job run` and tests; its tests built FakeAI without a name and it passed a nonexistent cfg.usage to run_pieces. Juniper-16 fixed both, added an incomplete-run test. Next: step 2, `megazword job status ID`.
- 2026-10-17: step 5 done by Juniper-16 (team.combine, `megazword job combine ID [--no-push]`). Plain push only: if job/ID already exists on origin it is left alone and reported. Reviewers exclude every family that wrote a piece.
- 2026-10-17: step 4 done by Juniper-16. A hard piece gets up to 3 free attempts, each starting with a new family; easy/medium keep one attempt with in-loop failover. Next for the heartbeat: steps 1-3, 6, 7.
- 2026-10-18: step 2 done by Juniper-16 (`megazword job status ID`, read-only). Step 7 sent to a free model directly with `megazword run --free-only -e` (no heartbeat needed). Tencent grants all used up.
- 2026-10-18: step 3 done by Juniper-16. The planner asks for a brief under 100 words (capped at 1500 chars, since every worker prompt carries it); old bare-list plans still parse. Step 6 sent to a free model as new files scores.py + tests.
- 2026-10-18: steps 6 and 7 done. All code steps (1-7) finished; only step 8 (a real job on Up Dawg, Phil said go) remains. Up Dawg is edotwedo/wake-up-laughing; its tests need `npm ci`, which needs Phil's permission rule, and job_workers worktrees need a shared node_modules.
