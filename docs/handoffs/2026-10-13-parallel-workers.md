# Handoff: `megazword job`, several AIs on one coding job (roadmap stage 2)

**Status:** open, for a Grok seat (Quill-12 or any Grok). Branch `grok/parallel-workers-2026-10-13`.
Written by Sorrel-12, 2026-10-13. Phil: "give grok a bigger job."

## Goal
Phil types one job ("add X to Mega Zword") and Mega Zword splits it, runs several AIs at
once, tests each piece, gets a review and hands Phil one result to approve. Free AIs take
the easy pieces.

## Build
1. `megazword job "<job>" [--workers N] [--project P] [--dry-run]`.
2. **Plan:** one AI (pick by `megazword plan`, prefer a strong one with room) splits the job
   into 1-N independent pieces as JSON: title, files it may touch, difficulty
   (easy/medium/hard), test command. Reject overlapping file sets; merge them into one piece.
3. **Workers:** each piece gets its own git worktree under `~\.megazword\jobs\<id>\<piece>`
   on branch `job/<id>-<n>`. Route by difficulty and live usage:
   - easy -> free API AIs through the new built-in coding loop
     (`src/megazword/agent.py`, branch `codex/free-agent-loop-2026-10-13`, merging soon;
     rebase on main once it lands),
   - medium/hard -> Codex / Claude / Grok CLIs.
   Run pieces in parallel (threads/processes), each with its own timeout.
4. **Mega Zword owns git, not the AI.** Workers only edit files. After each, Mega Zword runs
   the tests, commits on the piece branch, and records pass/fail. Reuse Night Shift's code
   for this (`src/megazword/night.py`: worktree, test, commit, push to a non-main branch).
5. **Retry:** a failed easy piece gets one retry on the next AI up (free -> paid).
6. **Review + combine:** merge passing piece branches into `job/<id>`; run the full suite;
   one AI with room reviews the combined diff (read-only); push `job/<id>`; never main.
7. **Report:** `megazword job status <id>` and a `job.json` with per-piece AI, time, result,
   and token estimate (feeds `stats`). Dashboard Jobs screen comes later (separate job).
8. Tests with fake AIs and a local bare repo (see `tests/test_night.py`). No paid calls.
9. GUIDE section "Jobs", STATUS entry.

## Lessons from today (Sorrel-12)
- Codex's Windows sandbox can't start the Store PowerShell. When launching `codex exec`,
  drop PATH entries matching `WindowsApps|PowerShell\7`. Also it can't write a worktree's
  git index, which is why Mega Zword must do the commits (step 4).
- Free models wander: in a live trial Cloudflare's Llama fixed the bug but never called
  finish and edited the test file. Treat "tests pass" as the success signal, and refuse
  test-file edits for pieces that aren't about tests.
- Gemini API returned 503 (busy) several times: retry with backoff.

## Rules
Own worktree only (this folder). Small commits, push this branch, not main. Tests:
`C:\Users\mrmar\mega-zword\.venv\Scripts\python.exe -m pytest -q`. Hand back in Q with the
branch name; Sorrel-12 or any seat reviews and merges.
