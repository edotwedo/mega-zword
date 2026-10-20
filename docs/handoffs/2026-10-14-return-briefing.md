# Return-to-terminal briefing

- Owner: Testlog-14 (Codex), explicitly assigned by Phil, 2026-10-14.
- Branch: `codex/return-briefing-2026-10-14`.
- Status: implementation complete; claim released.
- Done when: saved factual session cards can be published from CLI/MCP, read by
  a catch-up button, and shown once on an optional local camera return event.

Phil's idea: detect his return to the terminal and report each session's current
work, what just finished and what comes next. Implemented with no model calls:

- `megazword brief report --seat SESSION --project mega-zword --state working
  --doing "..." --done "..." --blocked "..." --next "..."` (one command line).
- `megazword brief` reads all cards. MCP `hive_status` accepts the same fields.
- Each card replaces that seat's previous report, atomically under a file lock,
  in `~/.megazword/briefings/`. Bounded fields, secret scrubbing, terminal-control
  removal, invalid-card handling and explicit stale labels (>30m).
- CLI `execute` reports run start, usable-answer return, failures and interruption.
  Uses MEGAZWORD_SEAT or run-PID. An answer is not claimed as verified delivery.
  Reporting errors cannot fail the run. Standalone terminal sessions must publish
  explicitly; AGENTS.md documents the convention. No transcript scraping or bots
  awakened to reconstruct history. Missing fields remain "not reported".
- Dashboard Catch me up dialog works from all views; reports are rendered as text.
  Lightweight camera/report polling is separate from usage-meter refreshes.
- CameraWatcher starts only from the token-protected enable action; off at startup.
  Local OpenCV 4 Haar face presence (any face, no identity recognition), downsampled
  to 320x240. No image API, recording, uploads or model calls. 15 seconds absence,
  2 seconds steady return, 120-second cooldown; fresh absence required after each
  return. Camera errors are visible. Disable/server shutdown closes the capture.
  Closing only a browser tab does not close the server; the header indicates camera on.
- Install `.[camera]` with the dashboard's Python, then restart. Existing system
  Python has opencv-python-headless 5, missing CascadeClassifier. Camera extra pins
  opencv-python >=4.8,<5. An isolated local environment verified OpenCV 4.14's
  bundled classifier and blank-frame detection without opening a webcam.

Validation:
- Full suite: 1123 passed in 193.20s.
- Final focused suite after the dependency guard and dialog event regression:
  27 passed. The dialog regression was added after the full-suite collection.
- Smoke: 36/36.
- Real Chrome browser: Catch me up button, dialog content, focus and layout verified
  against an isolated no-model dashboard. Preview server and tab then closed.
- No physical camera activated; detection/capture lifecycle used fakes. A physical
  device/lighting check is still required when Phil enables it.
- No edits to agent.py/night.py, free-worker assignment UI, shared installed checkout,
  or CODEX_JOB.md. The earlier log/rater combined work is already on main.

Deployment: update the installed checkout without overwriting others' config/free API
changes; use its Python to install `.[camera]` only if camera support is wanted.
Restart the dashboard to load the button; reconnect MCP sessions for hive_status.
Each standalone session should then publish one accurate card. This feature does
not promise awareness of terminals that never report, inject terminal keystrokes,
or start unrelated paid/free jobs.

## Physical camera fix, 2026-10-14 evening

Testlog-14 followed up after Phil's first return test failed. Existing Cedar
runtime at localhost8767 had missing cv2; installed opencv-python4.14.0.94 and
numpy into Cedar's isolated Python3.13 environment. Webcam then opened, but the
original detector missed Phil while seated: a live eight-frame local diagnostic
found zero faces with the old 320px/min40 pipeline, one face in every frame with
an aspect-preserving 640px/equalized/min24 pipeline. No frames were saved or sent.

The patch preserves aspect ratio, caps width at 640 without upscaling, equalizes
grayscale contrast, and detects smaller faces (min24, minNeighbors4). Tests model
a seated face at 10% of the frame width and cover 16:9, 4:3 and smaller input.
An unrelated Gemini fixture expired when UTC passed 2026-10-15; its assertion now
uses a clock matching the fixture instead of today's date. No quota logic changed.

The old 8767 process is elevated. Both normal and escalated Stop-Process returned
Access denied. Its camera was disabled and no jobs/room were running before the
restart attempt. Do not claim it was replaced or repaired. The corrected runtime
is at **http://127.0.0.1:8768**, using this seat's source via an ignored local helper
`build/briefing-runtime.py` and Cedar's isolated interpreter. No shared-checkout
edits or second camera capture remain. The 8767 process stays idle with camera off.

Verified end to end: corrected runtime reported face present, then return event 1;
the open browser's briefing dialog changed from closed to open without a manual
click. Phil confirmed he had looked away and returned, then said "cool".
Camera is still on locally in 8768. Existing stale seat reports remain labeled;
this does not establish that all terminal sessions are reporting.

Routine fix is local Gitea only (`origin`), following Phil's workflow. No GitHub
source mirror. CODEX_JOB.md remains untracked and uncommitted.

Validation of this fix: full suite 1141 passed in 169.99s on the isolated
Python3.13 interpreter; focused briefing/presence/dashboard suite 30 passed;
Gemini/presence suite after the clock correction 28 passed; clean diff check.
Existing Python3.13 is_reserved deprecation warnings remain unchanged.
