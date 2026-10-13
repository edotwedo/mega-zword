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
