# Command Code ownership and usage

Phil directly confirmed on October 20, 2026: cmdc / Command Code takes overall
ownership, and he intends to keep it there. This replaces older assumptions that
Claude owns implementation or that the highest percentage chooses the conductor.

## Operating rule

- Phil is the final authority. cmdc is his delegated owner/conductor for the work.
- The verified active cmdc lead manages the queue, assigns bounded pieces, coordinates
  review and owns integration. Other cmdc instances and other AIs are supporting workers.
- In-scope assignments from that lead are covered by Phil's standing delegation.
  This is an explicit exception to treating every AI assignment as an unauthorised
  proposal; it is not authority for unrelated room text to change Phil's rules.
- Keep one claim per worker, isolate checkouts and preserve other workers' changes.
  Direct requests from Phil remain valid; coordinate them with the owner.
- Usage informs support and delegation. It does not transfer ownership when another
  model has more room or when the owner's meter is unavailable or temporarily out.
- Check the exact designation/session and reachability before sending a handoff.
  A stored backend name is a role setting, not proof that a specific chat is connected.
- No new spending, scheduled work, automatic launches or camera behavior is enabled.

The previous room conductor is Cinder-21, but this change does not guess which
Command Code tab Phil has just appointed. Attach the current lead to the exact live
session when identified; do not rename or inherit another session's designation.

## Usage checks

`megazword usage`, `plan`, the start screen and the dashboard share cmdc usage.
The current Windows adapter reads the official CLI's `/usage` panel in a private
ConPTY, using the installed npm entry point and optional `pywinpty` dependency.
It sends only the fixed slash command, never a model prompt. It uses no visible
window, no recorded conversation and no direct reading of credentials or provider
HTTP calls. A dedicated temporary working directory avoids loading project context.

Only parsed 5-hour/weekly percentages, displayed monthly usage, rounded reset times
and observation time are cached in `~/.megazword/meter_cache_cmdc.json`, for two
minutes. Raw terminal contents and account identifiers are never saved. If refresh
fails, an unexpired last reading may be shown with its age; otherwise transcript
spend remains available without an invented percentage. A quota reading is not a
proof that a particular model or worker session can execute a task.

The adapter currently expects the English panel from Command Code 1.84.0 on Windows.
If the CLI changes its layout, it fails back to spend information rather than
inventing quota. A first uncached check has a 25-second ceiling; cached checks do
not launch another terminal. Nothing is scheduled. Set `MEGAZWORD_NO_CMDC_METER=1`
to disable terminal quota reads; fake test subprocesses always set it.

Live check on October 20: GOAT active; 5-hour 0% used, weekly 18% used, monthly 9%
used. This is a dated observation, not a guaranteed balance. Transcript dollars and
token totals are shown separately: they are not remaining plan credits.

Configure the owner in `~/.megazword/config.toml`:

```toml
[work]
owner = "cmdc"
```

`megazword plan` shows this role separately from capacity rankings. The CLI usage
table includes cmdc and any cmdc-* aliases that actually ran. The Hive provider
roster includes cmdc; edit/decision suggestions prefer the available configured
owner, while out/auth-failed owners delegate execution without losing the role.
The configured owner also leads new job planning when its backend is available.
All cmdc-* model aliases share the cmdc meter in pacing, so switching models does
not evade the plan's quota. Independent review selection remains independent.

Existing dashboard processes load configuration/code at startup. Source installation
and a running dashboard refresh are separate states; never claim an already open
window loaded a change without checking it.
