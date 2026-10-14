# Visible free-agent runs

- **For:** Cedar-14 implementation and validation; next seat for live free-job proof
- **Status:** taken by Cedar-14, 2026-10-14
- **Branch:** codex/run-controls-2026-10-14
- **Done when:** the existing Home run view exposes activity and cooperative intervention for free coding jobs, fake-model tests and full suite pass, and the change is published.

## Report

Phil authorized the next step unless a conflicting job exists. Checked Q, Hive,
active status and open PRs; no control-view owner found. PR54 was reviewed with
no findings and merged as 7e5e6db. Its Actions checks never started because of
account billing limits; local validation was 1096 tests and 36/36 smoke checks.

Home now has a free coding checkbox, explicit backend selection, a working-folder
label, current backend/model/requests, bounded activity, pause/resume and queued
instructions. Existing Cancel kills the process tree. Controls are cooperative:
an in-flight request/test completes before pause. An instruction received before
a pending write skips that model call and re-plans; native tool responses remain
valid. Instructions received during tests prevent premature completion. Paused
time is excluded from the agent wall cap. Local control files use atomic writes
and cross-process locks; event values are scrubbed and no code/instruction bodies
are included in event telemetry. Tests cannot inherit a real job's control path.

Large tool histories are condensed to plain JSON-tool protocol while preserving
task/user directions and recent observations. Rate-limit retry messages drive
cooldown length, with existing failover preferred; a wait that exceeds the wall
cap fails closed. User controls remain responsive during cooldowns.

Browser QA used a scripted preview (no live model spending) and verified Pause,
Resume, instruction queuing and activity rendering. Real fake-model tests prove
the instruction prevents the old write. Gemini API review returned 503; no review
success or free-model authorship is claimed for this implementation.

Focused suite: 201 passed. Smoke: 36/36. Final full suite in progress.

## Remaining limits

This controls new dashboard coding runs, not independent terminal sessions.
Interrupted jobs are not automatically restarted. Activity stays on this PC.
The existing Groq transport fix remains owned by PR52; no transport/default-model
duplication here. A later live HTTP queue completion must use that valid transport
and model configuration, retain a separate branch and report provider failures.
