# Handoff: chat tabs keep one real session (Phil, 2026-10-13)

**Status:** implemented by Alder-13 (Codex); validation and delivery below. Branch `codex/tab-sessions-2026-10-13`.

Problem (Phil): every message in a dashboard chat tab (`src/megazword/tabs.py`, sent via
`cli.execute`) starts a brand-new one-shot AI (`claude -p`, `codex exec`, grok one-shot).
It "just spawns some new one". Make each tab one continuing conversation.

## Build
1. Each tab stores the AI's session id after the first answer (in `tabs.json`).
   Following messages continue it:
   - Claude: `claude -p --output-format json` gives `session_id`; continue with
     `--resume <id>`.
   - Codex: `codex exec --json` gives the thread/session id; continue with
     `codex exec resume <id>`. Check `codex exec resume --help` for exact flags.
   - Grok: check `grok --help` for a resume/session flag; if none, keep today's behavior
     (history fed back in) and say so in GUIDE.
   - Free API backends: keep feeding history (they have no sessions).
   Verify flags against the real installed CLIs with `--help` only. Do not spend real
   prompts.
2. If a resume fails (expired/unknown id), start fresh once, store the new id, and show a
   small note in the tab.
3. When a tab resumes a session, send only the new message, not the whole history
   (saves tokens).
4. UI: show a small "session kept" marker in the chat view; "New session" button resets.
5. Tests with fake CLIs (existing test fakes in tests/), no real AI calls.
6. GUIDE.md: short section. STATUS.md entry.

## Rules
- Work only in this folder (a git worktree). Commit small steps on this branch. Do not
  push, do not touch main; Sorrel-12 tests, gets a review and merges.
- Tests: `C:\Users\mrmar\mega-zword\.venv\Scripts\python.exe -m pytest -q`. Known
  pre-existing failure: `tests/test_live_check.py::test_full_check_on_fakes`.
- Add a "Report" section at the bottom of this file when done.

## Report

Worker: **Alder-13 (Codex)**. Implemented in this worktree on the existing
`codex/tab-sessions-2026-10-13` branch. No Q posts, STATUS Active edits, startup
usage checks, real AI prompts, pushes or main edits.

- Tabs persist `session_id` and its backend. Claude JSON supplies the session ID;
  Codex JSONL supplies `thread.started.thread_id`, with the final answer read
  from `-o`; Grok gets a new explicit UUID via `--session-id` and later uses
  `--resume`. Free API/Gemini backends retain history-fed behavior.
- Resume sends only the new message. A missing/expired session gets one fresh
  attempt with recent history and a visible note; other errors use normal
  failure/escalation handling. Auto backend changes start with recent history.
- Chat view shows **session kept** and **New session**. Reset clears the saved
  session and recent tab history, preserves archived answers, and uses the
  authenticated `/api/tabs/new-session` endpoint.
- Per-tab locks refuse simultaneous sends/reset during an answer. Session epochs
  prevent a closed/recreated tab from receiving the old tab's answer. Accepted
  backend results now reach tabs directly, avoiding the shared `last_run.json`
  race. Shared CLI instances retain their original flags/state.
- GUIDE and STATUS entry updated; session adapters, fake CLIs, persistence,
  recovery, isolation, reset API and JavaScript controls covered by tests.

Installed-CLI flag verification used **help only**: `claude --help`,
`codex exec --help`, `codex exec resume --help`,
`codex exec -s read-only resume --help`, `grok --help`. Grok supports sessions;
no Grok history-only fallback was needed. Codex's `-s` stays before `resume`
because it belongs to the parent exec command; lean/model/config flags remain.

Validation:
- Focused suite: **96 passed, 2 deselected** (the two process-cancellation tests).
  Includes real subprocess calls to this repository's fake CLI shims, with
  temporary session files and no network/paid calls.
- `scripts/smoke.py`: **36/36 passed**.
- `git diff --check`: passed.
- Full suite: **808 passed, 5 failed, 9 setup errors** in 222 seconds. It was
  collected before the final five extra session tests; those pass in the final
  focused run above. Failing tests: Codex live silent-server fallback, Windows
  registry user-path test, two dashboard cancellation tests, and dashboard
  child cancellation in `test_timeouts.py`. Nine Night Shift tests failed at
  setup because Git could not clone their temporary local bare repositories:
  Git's `sh.exe` reported `couldn't create signal pipe, Win32 error 5`.
- Untouched HEAD snapshot reproduced **all five full-suite failures** and the
  Night Shift clone setup error (one representative test of that shared
  fixture). These are baseline failures in this environment. The handoff's
  known `test_full_check_on_fakes` failure passed in both the full suite and
  the baseline check.

**Commit blocked by sandbox.** Attempted staging and committing a working step;
both failed with `Unable to create
'C:/Users/mrmar/mega-zword/.git/worktrees/codex-tabs/index.lock': Permission denied`.
The worktree's Git index is outside this sandbox's writable folder. All changes
remain uncommitted, including the new handoff/report, adapter and tests. No push
was attempted. Git commands used a per-command safe.directory setting for this
worktree; no global Git configuration changed.

Next for Sorrel-12: inspect this worktree's diff and Report, stage the changed
files plus `src/megazword/tab_sessions.py`, `tests/test_tab_sessions.py` and this
handoff, commit on the existing branch, then perform the lead's review/merge
workflow. Do not replace STATUS's Active line with this finished worker.

## Fix pass 2 (Sorrel-12, from Grok's review, 2026-10-13)
1. tab_sessions.py ~84 (med): after a good Claude/Codex answer, a missing/unparsed session_id / thread.started raises, so the answer is dropped. Fix: return the answer anyway, store no session id, next turn starts fresh with history. Test it.
2. tab_sessions.py ~33 (med): with a saved session, only the raw user line is sent, so "include project memory" (context) never reaches the CLI on follow-ups. Fix: resume with the same new-turn payload (context block + message) the first turn would get, minus the old history. Test it.
Add "Report 2" when done.

## Report 2

Worker: **Juniper-13 (Codex)**. Completed Fix pass 2 in this folder.

- Claude/Codex answers survive missing, blank or invalid session metadata. The
  saved session is cleared; the next turn starts fresh with recent tab history.
  Empty answers and malformed Claude answer JSON still fail normally.
- Resumed Claude/Codex/Grok turns receive current project memory when requested,
  followed by the new message, without the old conversation history. Recovery
  after an unavailable session still uses the full recent history.
- Regression tests cover metadata loss on both first and resumed turns, history
  restoration, refreshed memory on follow-ups, and disabling memory again.
- Validation: **55 passed** in the session/tab suite; **113 passed, 3 deselected**
  across session, tab and dashboard integration/UI tests (`-k 'not cancel'`,
  excluding the environment's known cancellation failures). `git diff --check`
  passed. All CLI calls used fakes; no real AI prompts.
- Changes remain **uncommitted**, as Phil requested. Startup/coordination steps
  were skipped; no commit or push was attempted.
