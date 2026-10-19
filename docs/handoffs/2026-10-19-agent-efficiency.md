# Agent efficiency: make Mega Zword's loop behave like the Command Code loop

Date: 2026-10-19 (Lumen-20). Owner: **Juniper-16** (`src/megazword/agent.py`).
Reviewer: Fathom-19. Context: a full night of builds/deploys/audits ran on ~3% of
one plan; these are the levers that made that possible.

## Already present (do not redo)

- `search_files` + line-ranged `read_file` (`start`/`end`).
- A byte-identical system prompt every step so providers bill the cached prefix
  (`agent.py:668`, `agent.py:718`).
- History budgets: `HISTORY_CHARS = 90_000` (`:165`), `SMALL_HISTORY` per model.
- `COMPACT_EVERY = 10`, progress note, condensed reads (`:921-933`).
- Step caps, `JOB_CHAR_CAP`, model dropped after 4 bad replies.
- `run_tests` only for edited files.

## Gaps, highest value first

1. **Per-step tool-output budget (biggest win).** Today `SEARCH_HITS = 60` (`:183`)
   and `read_file` returns a fixed large slice. Cap the *total* tool characters per
   step (e.g. 24k; 8k for small models). Truncate **head + tail** (keep the error at
   the end of a log), return a one-line stub when the same path+range is read again,
   and hash tool results so an identical resend is not paid for twice.
   This is the same failure mode that burned the Tencent grants.

2. **Run independent tool calls in parallel.** The loop already accepts several calls
   per step; execute read-only calls (`list_files`, `search_files`, `read_file`)
   concurrently, keep writes and `run_tests` sequential. Fewer rounds, same tokens,
   friendlier to free-tier rate limits.

3. **Prompt discipline** (`SYSTEM_PROMPT`, `:114-130`). Add, without changing the
   cached prefix mid-job: "Act, do not narrate. Smallest diff that passes tests. Do
   not restate the plan. Stop as soon as the tests pass and finish."

4. **Per-step cost telemetry.** `prompt_chars` is logged; also log tool-result chars
   per step. Warn and auto-trim the oldest tool results when one step resends more
   than ~40k chars. Silent growth is how a job goes from cents to dollars.

5. **Verify with tools, not by reading.** Prefer `run_tests` to prove a change. Add
   project-configurable `run_build` / `run_lint`. Never ask a model to "check by
   reading" when a command can answer.

6. **Route by task shape.** Mechanical edits/docs/tests to the cheapest capable
   model (the `scores` table already ranks models by pieces that passed); design and
   debugging to the strong model. Keep the per-job cap.

## How to measure

Track est_tokens per step, steps per job, and the scoreboard pass rate
(`megazword job scores`). Success = the same pass rate at **60% or less** of the
tokens, with no increase in bad/no-op steps.
