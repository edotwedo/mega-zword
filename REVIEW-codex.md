# Reed-09 review for Kestrel

Branch: `codex/review`. Scope: dashboard.py, dashboard.html, answers.py,
doctor.py and scripts/install.ps1. README.md and runlog.py were not edited.

## Fixed findings

1. **Finished jobs could lose their last output.** The waiter published the
   exit code before stdout/stderr readers finished, causing browsers to stop
   polling early. It now joins both readers before publishing completion.
   Regression: holds readers until after process exit and checks the final answer.
2. **Cancel left backend children running.** It killed the Python CLI wrapper
   alone. Windows now uses taskkill /T /F; POSIX starts a process group and kills
   that group. Regression: a wrapper launches a sleeping child with inherited
   output pipes, then cancellation must complete and close those pipes.
3. **Concurrent requests could collide or lose control of running jobs.** Job
   allocation and state snapshots now share a lock. The retention limit removes
   completed jobs only; if all slots are running, new requests get a clear error.
   Regressions: parallel starts and retention with active jobs.
4. **Malformed API input disconnected requests or blocked a handler.** JSON
   arrays/scalars and list-valued models were not validated; negative lengths
   could read until EOF; oversized bodies were silently truncated. They now get
   JSON 400/413 errors. Launch/filesystem OSErrors return JSON 500 errors.
   Regressions send these requests to a real local HTTP server with fake jobs.
5. **Remote authentication could fail with an otherwise valid header.** A stale
   cookie took precedence over X-MZ-Token. The explicit header now takes precedence
   over cookies. Malformed cookies return forbidden instead of raising CookieError.
6. **Saved answers could overwrite each other.** Multiple CLI processes used an
   unlocked read/modify/write. A process lock and atomic replacement now preserve
   concurrent writes; readers share the lock for Windows replacement compatibility.
   Non-object JSON records are skipped, and nonpositive retention is rejected.
   Regression: four real Python writers preserve all 20 distinct answers.
7. **Run-log fields could inject HTML or break rendering.** prompt_chars and
   answer_chars were inserted without escaping; string seconds raised on toFixed.
   The counts are escaped and seconds are converted to a number. Regression
   executes the actual rendering JavaScript in Node with an HTML injection payload.
8. **The 24-hour chart undercounted busy days.** It counted only the last 60
   displayed records. It now uses the existing runlog summary over the full day.
   Regression: 75 recent runs yield a chart total of 75 while the table stays capped.
9. **Doctor crashed on valid TOML with wrong config types.** Integer routes,
   non-string backend names and non-string rater models now produce FAIL config,
   then diagnostics continue using defaults. Three config regressions cover this.

## Inspected without a confirmed defect

- Local Host validation and per-launch POST token: unauthorized POSTs and foreign
  hosts are refused by existing HTTP tests. Remote mode deliberately permits
  nonlocal Host values and authenticates reads; its POSTs still require the header.
- Prompt, answer, project-memory and job text rendering already escapes text.
  Tokens are generated from a URL-safe alphabet. No change was needed there.
- Installer: reviewed pipx and venv paths, exit-code handling and PATH deduplication;
  PowerShell parser reports no errors. No installer defect was reproduced. An
  actual install/PATH mutation was not performed as part of this review.

## Validation and limits

Validation uses the project's existing venv with `PYTHONPATH=src`; pytest uses
fake backends/meters, local HTTP servers and ordinary Python child processes.
No paid AI calls. Windows process-tree cancellation is exercised on this machine;
the POSIX branch is not exercised here. Remote auth is tested on local HTTP,
not through a phone/Tailscale connection. Node rendering tests use a minimal DOM
stub, not a full browser. This is a bounded review, not a complete security audit.

Full suite: **167 passed in 15.27s**. `git diff --check`: clean.
Installer PowerShell parser: no errors.

## Next step

Kestrel: review/cherry-pick the fix commit from `codex/review`, then merge on your
main worktree. No routing defaults or paid-model settings changed. Manuscript
work remains paused. Candidate follow-up: handle dashboard GET failures and
client polling errors gracefully when files are unreadable or the server restarts.
