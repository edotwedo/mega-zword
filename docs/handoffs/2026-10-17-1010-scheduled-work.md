# One-time 10:10 AM roadmap work

**Status:** scheduled, not running; prepared by Alder-16, 2026-10-17.
**For:** existing Mega Zword Night/heartbeat execution, with Claude subscription fallback.

Phil is at work and explicitly asked for this schedule. It is not a reminder.

- Task: `MegaZword-Work-2026-10-17-1010`.
- Exact start: 2026-10-17 10:10 AM America/Los_Angeles (-07:00).
- End: 12:10 PM; supervisor kills its owned worker tree at the deadline.
- Task Scheduler state verified Ready; next run and stored trigger both 10:10.
- Runs as Phil's existing signed-in Windows session, limited privilege. Locking is fine;
  signing out or shutting down prevents execution. WakeToRun and StartWhenAvailable are on;
  late starts after 12:10 exit without working.
- Executable: canonical app venv pythonw.exe; script and state below.

## Scope and execution

At most three steps, with no sleep/retry loop, each reading the latest local Gitea
main roadmap and handoff. Current next step: Credit Scout #4, step 6 (`scout --test`).
Do not repeat finished steps. Mark Scout complete only when acceptance requirements
are met, then the next roadmap item can receive one small tested foundation.

Uses existing Night worker worktrees, baseline/full tests, secret checks and two
completed free reviews before a fast-forward merge to local Gitea main. Free models
write code; Claude is the sole subscription fallback, with existing fresh-meter and
15% remaining gates. Codex, Grok, Antigravity and routine Tencent grants are excluded.
The source runtime is this dedicated Alder worktree, separate from the shared checkout.

Stop on failure, insufficient time, STOP or an active seat; leave branch/log evidence.
No accounts, key migration, billing settings, GitHub publication, chat messages or
new recurring schedules. Successful merged work may be built and installed in both
Python environments; existing chats/app processes are not closed or restarted.
Saved user routes/settings are preserved for a later reconciliation, not overwritten.

## Local files and controls

Folder: `C:/Users/mrmar/AppData/Local/MegaZword/ScheduledWork/2026-10-17-1010/`

- `run.py`: exact runner; `--preflight` performs no model work.
- `verify.py`: fakes verify excluded backends, early-launch guard and stop after failure.
- `status.json`: scheduled/running/completed/stopped/failed/time-limit, with outcomes.
- `run.log`: execution output, created when the task starts.
- `task.xml`: exported Task Scheduler definition.
- `STOP`: creating this file prevents starting the next step.
- Existing `~/.megazword/night/STOP` is also honored.

Disable before start: `Disable-ScheduledTask -TaskName MegaZword-Work-2026-10-17-1010`.
For immediate cancellation while running, end this task and its owned process tree.
No other scheduled task was re-enabled. Do not infer completion from Ready or exit 0;
read status.json, run.log and the saved branches/tests.

## Preparation verification

Preflight selected #4 Credit Scout from current main. Fake checks passed with zero
model calls. Windows UTF-8 decoding was corrected after the first preflight failed.
Exact task action, date/time, Interactive logon, wake flag and two-hour-five-minute
Task Scheduler fallback limit were read back. The runner's own fixed deadline is 12:10.

Usage at setup: Claude 8% five-hour / 14% weekly used; Codex 12% / 58%; Grok 95%
weekly; Antigravity out. Meters are refreshed before each scheduled step and before
Claude fallback. No automatic future Codex session or app automation was created.
