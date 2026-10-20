# Agent efficiency: make Mega Zword's loop behave like the Command Code loop

Date: 2026-10-19 (Lumen-20). Owner: **Lumen-20** (`src/megazword/agent.py`).
Context: a full night of builds/deploys/audits ran on ~3% of one plan; these are the
levers that made that possible.

## Already present (do not redo)

- `search_files` + line-ranged `read_file` (`start`/`end`).
- A byte-identical system prompt every step so providers bill the cached prefix.
- History budgets: `HISTORY_CHARS = 90_000`, `SMALL_HISTORY` per model.
- `COMPACT_EVERY = 10`, progress note, condensed reads.
- Step caps, `JOB_CHAR_CAP`, model dropped after 4 bad replies.
- `run_tests` only for edited files.

## Changes

1. **[DONE 2026-10-19] Per-step tool-output budget.** `STEP_TOOL_CHARS = 24_000`
   (`SMALL_STEP_TOOL_CHARS = 8_000` for low-TPM free tiers). Results are clipped with
   `_clip_result` (head + tail, so the end of a log survives), and a step whose budget
   is spent returns a short stub instead of another wall of text.
2. **[OPEN] Parallel read-only tool calls.** The loop already accepts several calls per
   step; execute `list_files` / `search_files` / `read_file` concurrently, keep writes
   and `run_tests` sequential. Same tokens, fewer rounds, friendlier to rate limits.
3. **[DONE 2026-10-19] Prompt discipline.** The system prompt now says: act, do not
   narrate; call tools instead of restating the plan; make the smallest diff that
   passes the tests.
4. **[DONE 2026-10-19] Per-step telemetry.** Each step emits a `step` event with
   `sent_chars` and `tool_chars`, so a regression is visible in the run log instead of
   only on the bill.
5. **[OPEN] Verify with tools, not by reading.** Prefer `run_tests`; add
   project-configurable `run_build` / `run_lint`; never ask a model to "check by
   reading" when a command can answer.
6. **[OPEN] Route by task shape.** Mechanical edits/docs/tests to the cheapest capable
   model (the `scores` table ranks models by pieces that passed); design/debugging to
   the strong model. Keep the per-job cap.

## How to measure

`megazword job scores`, plus est_tokens per step and steps per job in the run log.
Success = the same pass rate at **60% or less** of the tokens, with no rise in bad or
no-op steps.
