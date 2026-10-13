# Handoff: built-in coding loop so FREE AIs can code (Phil's top priority, 2026-10-13)

**Status:** implemented locally by Aster-13 (Codex worker for Sorrel-12). Branch `codex/free-agent-loop-2026-10-13`. Uncommitted: sandbox blocks the worktree index. Not pushed.

Phil insists free models become part of the coding workflow. Today the free API
backends (`src/megazword/free_apis.py`: groq, gemini-api, mistral, cloudflare, zai,
nvidia, openrouter, and local Ollama if present) can only answer text. They have no
coding CLI, so `megazword run -e` can't use them. Build Mega Zword's own agent loop.

## Build
1. `src/megazword/agent.py`: a tool loop over any OpenAI-compatible chat backend.
   - Tools: `list_files(glob)`, `read_file(path, start?, end?)`, `write_file(path, text)`,
     `replace_in_file(path, old, new)` (exact, must match once), `run_tests()` (runs ONE
     configured command, default `python -m pytest -q -x`, with a timeout; output tail
     only), `finish(summary)`.
   - Prefer native tool calling (`tools` param). Many free models don't support it or do
     it badly: fall back to a plain-text protocol (one JSON object per reply, fenced),
     detected automatically or per backend.
   - Confinement: every path is resolved and must stay inside the work folder; refuse
     `.git/`, `.env`, and anything outside. No shell besides the one test command. No
     network tools.
   - Limits: max steps (default 30), max chars per tool result, per-call timeout, total
     wall-clock cap. Stop cleanly and report on any limit.
   - The existing B15 secret guard (`guard.scrub`) still applies to trains-on-data
     backends' prompts and tool results sent to them.
   - Logs each run to the normal run log so `megazword stats`/usage counting see it.
2. Wire it in: `megazword run -e -m groq "job"` (and auto-pick with `-e`) uses the agent
   loop for API backends instead of refusing. The CLI coders (claude/codex/grok) keep
   their current path. Print a short summary and `git diff --stat` at the end. Never
   commit.
3. Tests (`tests/test_agent.py`): a scripted fake model, no network, no paid calls.
   Cover: edit + tests pass + finish; path escape refused; `.git`/`.env` refused;
   step cap; text-protocol fallback; bad JSON recovery; secret scrub for trainers.
4. Docs: GUIDE.md section "Free AIs that code", STATUS.md entry, one line in
   docs/DECISIONS.md not needed (Phil's direction is already logged).

## Rules
- Work only in this folder (a git worktree). Commit in small steps on this branch. Do
  not push, do not touch main; Sorrel-12 tests, gets a review and merges.
- Run tests with `C:\Users\mrmar\mega-zword\.venv\Scripts\python.exe -m pytest -q`
  (pyproject sets pythonpath to src). Keep the whole suite green except the known
  pre-existing failure `tests/test_live_check.py::test_full_check_on_fakes`.
- No real API calls in tests. Never print or commit keys.
- Plain English in docs, short sentences (Phil reads them).
- When done, add a "Report" section at the bottom of this file: what works, what
  doesn't, how to try it (`megazword run -e -m groq "..."`), test count.

## Report

Implemented all six tools, native OpenAI tool calling and automatic JSON fallback.
API backends use the loop in edit mode, including when the normal route picks
one. Local Ollama uses JSON replies. CLI coders keep their existing path. Paths
are resolved inside the work folder; `.git`, `.env` files, outside symlinks and
hard links are refused. Only the configured test command can run. Step, output,
call, test and wall-clock caps stop cleanly and leave edits for review. Training
backends get `guard.scrub` on message text and tool results before every call.
The normal log records requests and token estimates; stats count the requests.
GUIDE and STATUS are updated. No decision was added.

Try from the work folder, with the provider key already set:

```powershell
megazword run -e -m groq "Fix a small bug in this folder. Run tests and summarize the diff."
```

Use the installed command after Sorrel installs the reviewed source. For this
worktree before installation, run its source with:

```powershell
$env:PYTHONPATH = "src"
& C:\Users\mrmar\mega-zword\.venv\Scripts\python.exe -m megazword.cli run -e -m groq "Fix a small bug. Run tests and summarize the diff."
```

For local Ollama, use `-e -m ollama` with the configured model pulled. Settings
live under `[agent]` and `[free.ollama]` in the user's config. Native-tool rejection
on HTTP 400/422 switches to JSON. A bad native JSON argument also switches to
text. Provider availability, quota and real model quality were not tested live;
all model tests use fakes. The test command executes project code with normal
user permissions; it is not an OS sandbox. `git diff --stat` does not include
new untracked files. Stats count requests with the coding run's final outcome.

Focused validation: **103 passed** across agent, API, CLI, run-log and stats tests.
Full suite: **814 passed, 5 failed, 9 setup errors**. This full run preceded two
additional passing agent tests and the final protocol/diff-output refinements;
the focused run covers those changes. `git diff --check` passes.

The full-suite failures are in unchanged Codex live-meter, Windows registry and
dashboard cancellation tests. All nine errors come from Night Shift's local Git
clone fixture. A separate clone probe reports `couldn't create signal pipe,
Win32 error 5` from Git's shell. The handoff's known live-check failure did not
occur in this run. A comparison using an archive of this branch's original
`HEAD` source reproduced all five failures and the same Night Shift setup error
(`5 failed, 1 error` across those six checks). The other eight Night Shift errors
use that same fixture. These blockers also exist without the coding-loop changes.
The temporary original-source copy remains in `.baseline-verify/`. Automatic
approval review rejected its cleanup command as `blocked by policy`. It contains
only archived source for comparison; do not stage it. Sorrel can remove it outside
this worker's sandbox.

Git staging and commit were attempted with a command-local safe-directory setting.
Both failed: `Unable to create 'C:/Users/mrmar/mega-zword/.git/worktrees/codex-agent/index.lock': Permission denied`.
The index is outside the allowed write root. All changes remain uncommitted.
Nothing was pushed; no coordination post, usage check or STATUS Active edit was made.

Next step for Sorrel-12: review `src/megazword/agent.py` and the related diff, rerun
the suite outside the restricted worker sandbox, then stage the new agent/tests
and this handoff along with the tracked changes. Commit on the current branch;
review before merging. No live provider success is claimed here.

## Fix pass 2 (Sorrel-12, 2026-10-13 16:15) -- live trial findings
A live trial on a toy repo (calc.py add() bug + one pytest test) showed:
1. **Cloudflare Llama fixed the bug but never called finish** and ran to the 30-step cap.
   Fix: after any edit, when run_tests passes, end the run as success automatically
   (summary = last assistant text or "tests pass"). Also nudge the model: when it repeats
   the same tool call 3 times, tell it to finish.
2. **It appended `test_add()` to test_calc.py.** Fix: refuse edits to test files
   (`test_*.py`, `*_test.py`, `tests/`) unless the job text mentions tests; the
   refusal message tells the model why.
3. **gemini-api returned HTTP 503 twice** (Google busy). Fix: retry 429/500/502/503 with
   backoff (2s, 5s, 10s) inside the loop's model call, then fail as now.
4. **ollama returned 404**: Phil's PC has only `qwen2.5:1.5b` pulled. Fix: if the
   configured model is missing, ask Ollama's `/api/tags` and use the first installed
   model, printing which one; tests with a fake.
Same rules as above. Add a "Report 2" section when done.

## Report 2

Fix pass 2 is implemented in this folder. Changes remain uncommitted, as Phil
requested. Startup and coordination were skipped; Sorrel-12 owns those steps.

After a successful file edit, a passing test command ends the run automatically.
The summary uses the latest plain assistant text, or "tests pass" when the model
only sends tool JSON. Passing tests without an edit do not end the run. Failed
tests leave the loop running. Three identical tool calls in a row prompt the model
to finish, including calls in a batch.

Both edit tools refuse `test_*.py`, `*_test.py` and files under `tests/` unless the
job mentions test, tests, testing, pytest or unittest. Names are checked without
case sensitivity, before and after resolving symlinks. Reads remain allowed.
The refusal explains that the model should fix the implementation instead.

HTTP 429, 500, 502 and 503 retry after 2, 5 and 10 seconds. Retries stay inside the
wall-clock cap and each request is counted for logging. API HTTP errors retain
their status without exposing response bodies or credentials. Other statuses
fail immediately, apart from the existing native-tool fallback.

When an Ollama generation returns 404, the loop reads `/api/tags` and uses the
first installed model in server order. It prints the chosen name and keeps using
it for the run. The configured model is unchanged. An empty model list fails
clearly. This fallback is attempted once per run.

Try from a toy work folder, with the provider key already set:

```powershell
megazword run -e -m groq "Fix the addition bug in calc.py."
```

Use the source invocation from Report above until Sorrel installs this version.
Include "tests" in the job when test-file edits are intended. Use `-m ollama` to
try the installed-model fallback. No live model call was made during this pass.

Focused validation: **134 passed** across agent, API, CLI, run-log and stats tests.
The new tests use scripted models and fake HTTP responses. They cover automatic
success, failed tests, test-file restrictions and symlinks, repeated calls and
batches, all four retry statuses, exhaustion, the time cap, actual chat-client
status propagation and Ollama's server-order fallback. `git diff --check` passes.

Full suite: **843 passed, 5 failed, 9 setup errors** in 228.64 seconds. It started
before the final batch/symlink refinements and four additional regression cases;
the final focused run covers those changes. The five failing checks are:

- `tests/test_codex_live.py::test_silent_app_server_times_out_and_falls_back`
- `tests/test_codex_review.py::test_add_user_path_keeps_vars_duplicates_and_is_idempotent`
- `tests/test_dashboard.py::test_real_job_cancel_kills_process`
- `tests/test_dashboard.py::test_cancel_stops_backend_child_too`
- `tests/test_timeouts.py::test_dashboard_cancel_kills_the_ai_underneath`

All nine setup errors are in `tests/test_night.py`: its local Git clone fixture
exits with status 128. These are the same failing areas recorded in Report's
baseline comparison. No unrelated fixes were made. The known live-check failure
did not occur. Sorrel's next step is to review this uncommitted diff, rerun outside
the sandbox, and commit after review. No staging, commit or push was attempted.

## Fix pass 3 (Grok review, 2026-10-13) -- do after pass 2
1. HIGH agent.py ~139: run_tests runs pytest in the writable folder with the parent env; the model can write conftest.py/pytest.py that prints os.environ (API keys) back to itself. Fix: run the test command with an env stripped of key/token/secret vars (all known *_API_KEY, *_TOKEN etc. plus anything matching KEY|TOKEN|SECRET|PASSWORD), `python -I`-style isolation where possible, and always guard.scrub test output for every backend (not only trainers).
2. med ~119: list_files resolves the glob as a path; `*`/`?` raise WinError 123 on Windows. Validate as a pattern (reject `:`, `\`, NUL, `..`), don't resolve it.
3. med ~172: deadline = min(wall_timeout, self.timeout), so per-call timeout caps the whole run. Use wall_timeout for the run, call_timeout per call.
4. med ~205: list-type `content` (multi-part) crashes on .strip(). Treat non-str as an invalid reply (nudge, continue).
5. med ~221: non-list/oversized tool_calls raise out of _run. Treat as invalid reply.
6. low ~159: cap write_file size (e.g. 200 KB).
Tests for each. Add "Report 3".
