# Handoff: free bots pace themselves and get a quality check (Sorrel-12, 2026-10-13)

**Status:** queued for a Codex worker at 17:46 (after Codex's 5-hour reset). Branch `codex/free-pacing-2026-10-13`.

The built-in coding loop (`src/megazword/agent.py`) is on main. First live runs showed:
1. **Rate limits:** gemini-api and mistral hit HTTP 429 within a minute; the loop sends requests back to back.
2. **Fake passes:** Cloudflare's Llama wrote tests that were all `assert True`; they "passed".

## Build
1. **Per-provider pacing** in the loop: a minimum gap between model calls per backend, from config `[agent.pace]` (seconds), with defaults: gemini-api 6, mistral 2, groq 2, cloudflare 1, openrouter 3, nvidia 2, zai 2, ollama 0. Shared across processes via a small file under MEGAZWORD_HOME (filelock.py exists) so parallel workers on the same provider don't burst.
2. **Quality gate** before a run counts as success when the job touched tests: parse the new/changed test files with `ast`; reject if any test function has no assert/pytest.raises on something other than a constant (`assert True`, `assert 1`), or calls nothing from the module under test. On reject, tell the model exactly why and continue the loop (counts toward caps).
3. Optional reviewer hook: `[agent] reviewer = "<backend>"`. When set, after success send the diff to that backend (read-only, one call) and fail the run if it answers REJECT with a reason. Default off.
4. Tests with fakes, no network. GUIDE lines. STATUS entry.

## Rules
Work only in this folder. Can't commit (sandbox): leave changes uncommitted and add a Report section here. Full suite: `C:\Users\mrmar\mega-zword\.venv\Scripts\python.exe -m pytest -q` (known unrelated failure `tests/test_dashboard_room.py::test_say_start_and_view`). Skip coordination/startup steps.

## Report

Flint-13 (Codex), 2026-10-13. Implemented in this folder. No coordination/startup
actions, commits, pushes, installs or live model calls were made.

### Changes

- `agent.py`: reserves provider call starts under `MEGAZWORD_HOME/agent-pace`
  with `filelock.locked` and atomic timestamps. Defaults match the Build list;
  `[agent.pace]` overrides accept finite nonnegative seconds. Calls, retries and
  API/local review calls share the provider's reservation. Lock failure or a wait
  beyond the wall cap stops the run without sending a request.
- `agent_quality.py`: AST checks on Python test files actually changed by file
  tools. Checks every test function in those files, including async/class tests.
  Rejects constant/empty assertions, syntax errors, missing tests, and tests with
  no imported production call. Handles import aliases, local helpers/fixtures,
  class instances and both forms of `pytest.raises`. Untouched tests are exempt.
  Explicit `finish` and automatic success after `run_tests` both use the gate.
  Rejection feeds file/test/reason back into the same capped loop. File edits
  invalidate the previous passing-test flag.
- Optional `[agent] reviewer`: one call with the complete diff of files edited
  during this run, including new files. Default off. API/local reviewers receive
  no tools; CLI reviewers are newly constructed without edit permissions, with
  Claude explicitly in plan mode and tools disabled. Review uses the remaining
  wall cap, call cap and reviewer timeout. REJECT, missing/invalid verdicts or
  reviewer errors fail the run. Training reviewers receive scrubbed content.
  An oversized diff fails instead of being silently truncated.
- `config.py`, `cli.py`, GUIDE and STATUS document and wire these settings.
  Added fake-model and concurrent-process tests; adjusted the existing test-edit
  permission test to write a meaningful test rather than invalid Python.

### Validation

- Latest focused command: `C:\Users\mrmar\mega-zword\.venv\Scripts\python.exe -m pytest -q tests/test_agent.py tests/test_agent_pacing.py`.
  **124 passed in 8.01s**, no warnings. Includes two simultaneous processes using
  the real file lock and fake clocks, retry pacing, wall/lock failures, gate
  rejection/repair on both success paths, configuration validation, CLI reviewer
  wiring, one-call reviewer failure, secret scrubbing and timeout bounds. Final
  edge checks distinguish new empty files from unchanged files and allow helper
  modules without requiring them to define test functions.
- `git -c safe.directory=C:/Users/mrmar/mz-seats/codex-pacing diff --check`: clean.
- Agent plus affected CLI regression checks: **265 passed in 12.78s** across
  `test_agent`, `test_agent_pacing`, `test_cli`, `test_free_apis`, `test_gemini`,
  `test_hive_import`, `test_meters`, `test_phone` and `test_sentinel`. These checks
  followed the fix for a local import that initially shadowed `default_backends`.
- Full suite: `C:\Users\mrmar\mega-zword\.venv\Scripts\python.exe -m pytest -q --tb=short`:
  **981 passed, 6 failed, 9 setup errors in 233.51s**, no warnings. The six failures
  and all nine Night Shift errors are outside the pacing/quality changes; see the
  untouched-baseline comparison below. The final empty-file/helper/diff-format
  refinements were followed by the focused checks above.
- Baseline comparison: exported untouched commit `1e66005` to a temporary
  directory and reran eight selected cases. **6 failed, 1 passed, 1 setup error
  in 134.53s**. All six remaining failure names and the representative Night Shift
  setup error reproduced without these changes:
  - `test_codex_live.py::test_silent_app_server_times_out_and_falls_back`
  - `test_codex_review.py::test_add_user_path_keeps_vars_duplicates_and_is_idempotent`
  - `test_dashboard_room.py::test_say_start_and_view` (known in the assignment)
  - `test_dashboard.py::test_real_job_cancel_kills_process`
  - `test_dashboard.py::test_cancel_stops_backend_child_too`
  - `test_timeouts.py::test_dashboard_cancel_kills_the_ai_underneath`
  - `test_night.py::test_three_job_dry_run` (setup error)
  `test_live_check.py::test_full_check_on_fakes` passed on baseline. A separate
  local bare-repo clone confirmed the setup failure: Git's bundled `sh.exe`
  reports `couldn't create signal pipe, Win32 error 5`, and clone exits 128.
  This is a sandbox limit; no Git configuration was changed to bypass it.
  Temporary baseline cleanup encountered a process holding its working directory
  open; an attempted later empty-directory removal was rejected by automatic
  approval review with `blocked by policy`. No shared project files were involved.

### Limits and delivery

The AST gate checks structure, not behavioral correctness. It recognizes
non-stdlib imports as production dependencies; dynamic imports, custom assertion
helpers and fixture wiring in other files may need simpler explicit calls.
Provider pacing spaces request starts; it does not guarantee a provider will
never rate-limit a request. Reviewer requests are included in the coding run's
total request count (the existing log attributes the total to the coding backend).
Review covers edits through the file tools, not side effects from the trusted
test command. These limits are documented or retained from the existing loop.

All changes remain uncommitted. Next step for the lead: inspect the nine changed
or new files shown by `git status --short` (including this previously untracked
handoff, `agent_quality.py` and `test_agent_pacing.py`), review the full-suite
failures above, then commit and deliver from this worktree. No shared worktree
was edited.
