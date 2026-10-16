# Repository cleanup — Cedar-27

Phil requested an audit of uncommitted changes, keeping useful work in commits
and removing obsolete work. All registered Mega Zword worktrees were checked.
The audit found 25 changed/untracked files across eight worktrees, plus the
explicitly excluded `CODEX_JOB.md` in `mz-seats/codex-test-log`.

## Preserved drafts

These are exact snapshots of the original changes on their original bases.
They are deliberately separate from main and the installed application.
They are unfinished, unvalidated drafts; no feature completion is claimed.

| Original worktree | Recovery branch | Commit | Disposition |
| --- | --- | --- | --- |
| `mz-tab-order` | `recovery/2026-10-16-tab-order` | `48b3e57` | Preserve atomic persistent tab ordering, HTTP endpoint and regression tests. Still needs integration/review against current main and UI work. |
| `mz-seats/grok-wall` | `recovery/2026-10-16-usage-pace` | `c2dc389` | Preserve optional `usage --pace` draft. Before any integration, review hardcoded seat aliases, stale/unknown meter handling and missing tests. |

Original dirty files were restored to each worktree's own HEAD only after
the recovery commits existed. No original branch was reset or checked out.

## Removed obsolete changes

| Worktree | Removed | Reason |
| --- | --- | --- |
| `mega-zword` | Changes to `config.py`, `free_apis.py` | Groq model default and curl transport already have newer committed implementations on current local Gitea main (`80278f0`, `9bf5c62`). Do not overwrite current provider/routing work with the old copies. |
| `mega-zword` | Untracked `scripts/setup-phil.ps1` | Personal, obsolete setup draft with a dated B14 wait instruction and optional scheduled Sentinel setup. No references require it. |
| `mz-lead` | `.coverage` | Generated coverage database. Added coverage ignores to prevent recurrence. |
| `mz-overnight-codex` | Two test diffs and `test_process_group.py` | Floor/process-group coverage already exists on main. Gemini alias test imports obsolete `extra_backends` and asserts an outdated default. |
| `mz-seats/grok-answers` | Untracked `test_answers.py` | Incomplete test lacks `json` import and incorrectly asserts rating is absent. Current main has broader tested answer-history coverage including rating. |
| `mz-seats/grok-free` | Two tracked diffs and `hive_window.ps1` | Older Groq workaround superseded on main. Alternative Terminal/startup/protocol registration experiment superseded by `workspace.py`; retaining another launcher would duplicate paths. |
| `mz-seats/grok-hive-resume` | Four tracked diffs and three untracked files | Earlier parallel restore implementation superseded by `workspace.py`. Uses a hardcoded Codex database version, collapses sessions by folder, and uses ambiguous continuation fallbacks. Do not add a second restoration path. |

File hashes and the expected dirty-file list were checked before cleanup to
detect concurrent changes. Only individually named files were removed; no
recursive cleanup, worktree removal, process closure or runtime restart.
Old worktrees remain on their original commits. Their contents were not
silently upgraded to main.

## Automatic activity

Follow-up: Phil requested Sentinel remain active if it does not consume AI
usage. The exact scheduled collector source was verified against this checkout:
it reads Windows events and makes HTTP availability/notification requests,
without invoking AI models. Re-enabled only `MegaZword-Sentinel` on its existing
five-minute schedule and requested one check. All other automatic jobs remain
disabled. The list below records the earlier blanket stop, before this exception.

Before this audit, at Phil's request, disabled:

- `MegaZword-FreeTools-Testlog14`: one-time free-model continuation.
- `MegaZword-Morning-FreeTools-Testlog14`: scheduled morning free-model runs.
- `MegaZword-NightShift`: overnight job runner.
- `MegaZword-Sentinel`: periodic system/service checks.
- `MegaZword-WorkspaceSnapshot`: periodic saved-session metadata snapshots.

Both owner-camera watcher processes were stopped and the Hive Startup shortcut
was moved out of Startup. Existing chats remain open. Do not re-enable helpers
as part of cleanup or interpret historical STATUS entries as current schedules.

## Verification

Final verification and delivery are recorded in `docs/STATUS.md`.
No automatic tasks, camera, UI windows or AI model jobs are started by this audit.
