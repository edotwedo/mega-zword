# Terminal workspace and app repairs - Testlog-14

Phil's scope is a terminal workflow, separate from dashboard saved status cards.

## Installed locally

- Desktop shortcuts: **Restore Hive**, **Catch me up - terminal**, **Enroll my face**.
  They target `pythonw.exe` and this checkout's `scripts/workspace_entry.pyw`.
- `MegaZword-WorkspaceSnapshot` records native session IDs, folders, models and
  roster metadata every five minutes. Manual scheduled run returned 0. No models
  run for snapshots; no transcript copy, generated batch code or credentials.
- Imported the four literal roster entries in the older local
  `~/.megazword/hive-resume.ps1` without executing or modifying that script.
  Combined with active Codex writer locks and Grok registry: six saved seats.
- Data stays under `~/.megazword/workspace/`. Closed seats remain saved through
  reboot. Exact IDs replace ambiguous `--last`/`--continue` restores.
- Restore now uses a dedicated **Hive** virtual desktop, never the existing
  **ai workshop** desktop. It waits for Windows to confirm the desktop switch,
  then makes one `wt -w new` invocation containing all eligible saved tabs.
  This requests a fresh Terminal window regardless of existing window names.
  Configured tab order,
  titles and colors survive restoration. Capturing drag-reorders, original tab
  color-picker choices, arbitrary panes and pixel positions is not implemented.
- Already-open writers are skipped. Existing unmanaged tabs are not controlled
  through keystroke injection. Close them when ready and use **Restore Hive** to
  get managed tabs. This chat was not terminated to demonstrate restoration.
- The existing Startup shortcut now runs **boot**, not camera-only **watch**:
  refresh the snapshot, request the full saved restore, then run the owner
  watcher. Startup refresh failure falls back to the saved roster; Explorer or
  Terminal launch failures get up to three attempts. Installing the shortcut
  does not execute it. This is an interactive login workflow, after Windows
  sign-in, not a pre-login service.
- Saved PIDs are checked against process creation time/client name so recycled
  PIDs after reboot do not hide seats. A frozen manifest gives each launch batch
  stable session/index mappings even if a five-minute snapshot changes.
- Missing folders/clients are recorded per seat instead of aborting other tabs.
  Local diagnostics: `boot-status.json` and `restore-status.json`. Launch request
  counts alone are not proof that every native client started successfully.

## Return summaries and owner recognition

- Restored tabs use their native CLI resume command with an 80-word status,
  completed-work, blocker and next-step prompt. These are real model requests
  when restored/returned, not during five-minute snapshots.
- A native ConPTY relay passes the interactive session through the visible tab.
  Return prompts wait for a native completed-turn record, fresh since the last
  submitted input, a quiet interval and an empty input line. Unknown states
  stay queued. Busy sessions and typed drafts are not interrupted.
- Manual **Catch me up - terminal** and owner-camera return publish one local
  return event. Only managed tabs can consume it; old standalone clients do not.
- Phil clarified **only him**, not his mother, children or other faces. The old
  dashboard generic-face camera at 8768 was turned off. New identity enrollment
  is deliberately manual: **Enroll my face**, only Phil in view, SPACE for five
  poses, ESC to cancel. Phil completed enrollment at 08:58:39 PT. The encrypted
  template was saved and the watcher started; a local `owner return` event was
  subsequently observed. Phil reported only one missing client opened, which
  matches the old behavior of skipping live seats and reusing ai workshop.
- YuNet detects faces; SFace compares local embeddings at cosine threshold .50.
  Templates are encrypted for Phil's Windows account using DPAPI. No frames or
  plaintext templates are saved, uploaded or sent to models. The local watcher
  starts after enrollment and through its Startup shortcut on later logins.
- Existing 15-second absence / two-second stable return / 120-second cooldown
  gates are retained. Non-owner rejection and the complete restored-terminal
  return workflow still need physical testing. Recognition is a convenience,
  not a security boundary.
- Public assets were downloaded from pinned OpenCV Zoo commit
  `47534e27c9851bb1128ccc0102f1145e27f23f98` and VirtualDesktopAccessor release
  `2024-12-16-windows11`. Model hashes match their Git LFS pointers; download
  URLs/hashes are recorded locally in `assets.json`. Models are Apache-2.0;
  desktop helper is MIT. Source links:
  https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface
  https://github.com/Ciantic/VirtualDesktopAccessor

## App correction

- Phil's actual open page was localhost8767, the older elevated Cedar runtime.
  Do not claim it was updated or stopped. Owned runtime/launcher target 8768.
- Chat plus preserves a separate input draft per tab. Original history remains
  stored on its existing tab. Delete controls are visible both beside tab names
  and in the chat header; deleting another chat leaves the selected one intact.
- Hive Send posts the message and starts replies in one request. Separate Start
  is gone from normal use; Resume replies appears only for a paused room.
- A sidebar build label distinguishes this deployment from older servers.

## Validation

**Latest correction:** unit tests mock all desktop switches, native launches,
and camera startup. Actual new-window/desktop/login behavior is intentionally
unverified until Phil's planned restart around **90% Codex five-hour usage**.
Do not reopen windows, switch desktops or restart to test it now. No automatic
restart or threshold timer was created. Phil drives interactive steps.

- Focused workspace/presence/briefing suite: 50 passed. This includes all-six
  batch launch, ai workshop exclusion, stale PID rejection, login ordering,
  snapshot fallback/retry, and frozen-manifest regressions.
- Full suite for this correction: **1172 passed in 179.25s**, 108 existing
  deprecation warnings. `git diff --check` passed. No live Terminal launch,
  desktop switch, camera/app restart or reboot was used for these checks.
- Startup shortcut readback confirms a windowless Python **boot** action; it
  was installed without invoking boot or restore.

Earlier validation (before the fresh-window/login correction):

- Full suite: 1158 passed in 156.62s, 108 existing deprecation warnings.
- Subsequent focused suite: 145 passed (includes additional workspace regressions
  and app build/control checks). Full suite predates the last two focused
  workspace regressions and the small launcher/relay follow-up fixes.
- DPAPI encrypt/decrypt roundtrip tested; face models loaded and rejected a
  blank image; native ConPTY input/output roundtrip passed without AI calls.
- Desktop helper enumerated both Windows desktops; switching to the existing
  ai workshop desktop and returning to the original desktop was exercised.
- Real Windows Terminal smoke test passed: a dummy TUI received exactly the
  queued 80-word catch-up instruction after a completed turn. No AI client was
  invoked. This exposed and fixed startup timestamp and terminal device-response
  handling; terminal protocol replies no longer look like a typed user draft.
- Owned 8768 server restarted only after confirming no active jobs or room.
  Live API reports source build `41270ca`. Phil's actual older8767 browser page
  was moved to8768, keeping selected chat t2. No unfinished draft was present.
  Browser visibly verified both delete controls, the build label, Hive Send and
  absence of a normal Start button. Screenshot: `build/updated-hive.png`.
- Desktop and Start-menu Mega Zword shortcuts now launch this checkout's
  `scripts/desktop_entry.pyw`, targeting8768. Prior shortcuts are backed up under
  `~/.megazword/workspace/shortcut-backups` when they existed.

## Operational notes

Keep this checkout and Cedar's isolated `.venv` available: shortcuts/tasks refer
to them. The shared installation remains owned by other seats and unchanged.
`CODEX_JOB.md` stays untracked. Routine Git delivery uses local Gitea only.

Phil objected to unannounced interactive terminal tests. They did briefly
switch desktops. No further UI actions were taken after his objection. New
AGENTS rule: warn first and wait for readiness before tests move keyboard focus,
open test windows or switch desktops. His mention of a spare computer does not
establish any remote setup, installation or authorization on that machine.

## Deferred reboot test: prompt Phil; do not take over

**Ready for Phil's restart, 2026-10-15 11:44 PT:** Codex meter93% used (7%
remaining). Snapshot refreshed: six seats, Grok/Claude/four Codex. All saved
folders, installed executable resolution, Python dependencies, owner template,
models and desktop helper passed a no-launch preflight. Startup boot action
read back successfully; snapshot scheduled task last result0. Source25c6491 is
saved on local Gitea main. No UI takeover or restart performed. Phil will do a
full restart and Windows update; resume verification when he says back.

1. When Phil is ready near 90% usage, save each active seat's state and refresh
   the snapshot. Coordinate any active work before he restarts Windows.
2. Phil restarts and signs in. Verify one fresh Terminal window with all six
   saved tabs on the dedicated **Hive** desktop, correct native session IDs,
   models, tab order and configured colors. Inspect individual failure reasons
   if any saved seat cannot resume.
3. Read boot/restore diagnostics and compare with actual native client state;
   do not infer success from launch-request counts.
4. Test Phil's 15-second absence/two-second return and the queued summaries in
   managed tabs, including a busy client and an unfinished input draft. Test a
   non-owner return separately if Phil chooses. Verify helpers stay invisible.
