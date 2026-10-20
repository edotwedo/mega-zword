# Silent background commands: Testlog-14

Phil requested an immediate fix for recurring command windows before continuing
the terminal workspace/camera workflow.

## Fixed and applied

- `MegaZword-Sentinel` was launching console `python.exe` every five minutes.
  Its existing task now uses sibling `pythonw.exe`. Triggers, identity and
  arguments remain unchanged.
- Its working directory is this seat's `src` directory, so `-m megazword.cli`
  loads the repaired code without changing another seat's shared installation.
  Keep this checkout available until the task is deliberately redeployed.
- Sentinel's PowerShell event-log reader and task-registration command now use
  `CREATE_NO_WINDOW`. Background project-name Git lookup and room summary GitHub
  CLI calls use the same flag. Output capture and error handling remain intact.
- `scripts/hide_background_tasks.ps1` inspects by default. Apply using
  `-Apply -UseWorktreeSource` from the checkout to use its source. It only accepts
  the expected single-action Sentinel task and verifies the resulting action.
  No schedules are added or removed; a missing logon task stays missing.

## Evidence

- Task source import resolved to this checkout's `src/megazword/sentinel.py`
  using the task's existing Python environment.
- Manually started the existing task; last run 2026-10-15 08:19:40 PT,
  `LastTaskResult=0`.
- Focused process/Sentinel/room tests: 49 passed. Added regressions assert hidden
  event-log and Git launches while preserving their returned data.
- Full suite: 1143 passed in 172.94s; 108 existing deprecation warnings.
  `git diff --check` passed.
- Existing dashboard jobs already use `process_group()` with hidden Windows
  launches; cleanup `taskkill` was repaired previously. Persistent browser
  native-host console processes were not established as popup sources and
  were left alone.

## Next

Continue terminal workspace
restoration and fresh per-session return summaries separately. A fresh return
summary across terminal instances is still outstanding; saved dashboard cards
do not fulfill that request.
