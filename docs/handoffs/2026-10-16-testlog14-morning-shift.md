# Mega Zword: 5-11 AM free-model shift

Owner: Testlog-14 (Codex). Phil requested useful Mega Zword work to continue
while he is at work on Friday, 2026-10-16, from 5:00 to 11:00 AM Pacific.

## Evidence used for the work queue

- Mega Zword's full audit is in the local answer history at
  `%USERPROFILE%\.megazword\answers.jsonl` (run 48). Phil's findings were:
  provider/model IDs are mostly static while `openrouter_catalog.py` only
  passively lists candidates; `_statements()` reparses prefixes (quadratic in
  config size) and gives a generic malformed-config error; `_edit_key()` adds a
  temporary `__mz_marker__`; identical writes no-op; file locking is imported
  only on the first write; and `parse_until()` accepts `d/h/m` and ISO dates,
  not seconds suffixes. The audit also praised TOML round-trip verification,
  atomic replacement, rollback, and separate thread/process locks.
- Treat those points as hypotheses, not confirmed bugs. A direct local
  reproduction with `[out].__mz_marker__ = true` successfully added another
  `[out]` key, so the marker-collision claim is not confirmed. No-op is correct
  when the desired value is already present; seconds suffixes are outside the
  documented `d/h/m` syntax; and parser complexity matters only if realistic
  config sizes make it slow. Do not make speculative fixes.
- `tencent_first()` sorts by local estimated tokens without considering saved
  low-quota marks, even though `free_apis.request_quota_low()` exists. Verify
  whether skipping marked models at this earlier routing layer is useful and
  safe.
- The audit's 429 finding appears stale: current provider handling preserves
  Retry-After/reset timing, and tests cover rate-limit messages. The scheduled
  task verifies this and should leave correct behavior alone.
- The audit recommended a next pass through `routing.py`, `pacing.py`,
  `agent.py`, `limits.py`, and `dashboard.py`, focused on failover order, tool
  loops, quota accounting, and threaded writes.
- `openrouter_catalog.py` already passively lists models whose catalog metadata
  says both prices are zero and tool calls are supported. It explicitly warns
  that catalog entries are not verified endpoints. The task may improve this
  candidate workflow, but must not activate or call a new provider.
- The earlier 11:43 PM public-URL tool task remains separate and must finish
  before its code is treated as complete. The morning's first model inspects
  its result and avoids duplicating it.

## Schedule and safeguards

Task Scheduler task: `MegaZword-Morning-FreeTools-Testlog14`. It launches the
hidden PowerShell runner hourly at 5, 6, 7, 8, 9, and 10 AM. Each slot runs one
fixed Tencent model sequentially, with `--free-only`, a 15-minute model cap,
and an outer hard stop at 11:00 AM. The order uses the local 365-day token
estimates at setup time, least-used first: DeepSeek V4 Pro (0), DeepSeek V4
Flash Vision (0), Kimi K3 (77,147), GLM-5.3 (209,861), GLM-5.3 Flash (215,938),
then Kimi K2.7 Code (217,659). These are rough Mega Zword log estimates, not
Tencent's authoritative balances. TokenHub's aggregate usage query had no
records. `endpoint get` cannot fetch the listed `VIRTUAL` model records, though
the read-only endpoint list showed pay-as-you-go disabled for all listed
endpoints. The task therefore uses local estimates for order, `--free-only`
for routing, and stops on a model/API failure; it does not claim an exact live
free-token balance.

After a code change, the runner runs the full pytest suite using the established
Python 3.11 test environment, with `PYTHONPATH` pinned to this seat's `src/`, an
isolated Mega Zword home, and provider credentials removed. It commits only `src/megazword/`,
`tests/`, and `docs/`, then pushes `HEAD:main` to local Gitea `origin`, after
confirming that origin is `127.0.0.1:3000`. It never pushes to GitHub. `CODEX_JOB.md`
is not read or staged. A test failure, model/API error, conflicting active
worker, or unexpected changed path stops later slots and records a local
blocked status. The next slot does not blindly retry a failed task.

No terminal, browser, or dashboard window is opened, and no desktop or keyboard
focus is changed. The task uses the current user's interactive Windows login
so it can read Mega Zword's existing local API configuration; leave the user
session logged in and the PC on/awake. `WakeToRun` and `StartWhenAvailable` are
enabled, but a reboot followed by no login can still prevent API access.

## Monitor or stop

```powershell
Get-Content "$env:LOCALAPPDATA\MegaZword\FreeToolsContinuation\2026-10-16-0500\status.json"
Get-ChildItem "$env:LOCALAPPDATA\MegaZword\FreeToolsContinuation\2026-10-16-0500\slot-*.log"
New-Item -ItemType File "$env:LOCALAPPDATA\MegaZword\FreeToolsContinuation\2026-10-16-0500\STOP"
```

Each model and test run has a separate log. The status file updates while a
slot is running and records the next scheduled slot. Dry-run validation makes
no model call. Do not claim the morning work completed until the final status
and logs are inspected.
