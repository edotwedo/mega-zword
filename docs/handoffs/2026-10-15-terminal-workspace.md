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
- Restore uses the existing **ai workshop** virtual desktop (or creates **Hive**
  if no such desktop exists) and a named Terminal window. Configured tab order,
  titles and colors survive restoration. Capturing drag-reorders, original tab
  color-picker choices, arbitrary panes and pixel positions is not implemented.
- Already-open writers are skipped. Existing unmanaged tabs are not controlled
  through keystroke injection. Close them when ready and use **Restore Hive** to
  get managed tabs. This chat was not terminated to demonstrate restoration.

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
  poses, ESC to cancel. Enrollment has not been completed by the agent.
- YuNet detects faces; SFace compares local embeddings at cosine threshold .50.
  Templates are encrypted for Phil's Windows account using DPAPI. No frames or
  plaintext templates are saved, uploaded or sent to models. The local watcher
  starts after enrollment and through its Startup shortcut on later logins.
- Existing 15-second absence / two-second stable return / 120-second cooldown
  gates are retained. Physical owner/non-owner acceptance still needs testing
  after Phil enrolls. Recognition is a convenience, not a security boundary.
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
- Final live app deployment evidence is recorded below after completion.

## Operational notes

Keep this checkout and Cedar's isolated `.venv` available: shortcuts/tasks refer
to them. The shared installation remains owned by other seats and unchanged.
`CODEX_JOB.md` stays untracked. Routine Git delivery uses local Gitea only.
