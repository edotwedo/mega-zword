# Automatic Codex session designations and tab titles

**Status:** done by Alder-16, 2026-10-17. Code f647027 + 6b8bc62.
**For:** Phil, future local Codex sessions and Juniper-16 as Mega Zword owner.

Phil explicitly requested that every new terminal instance choose its designation
and put it in the tab automatically. This replaces manual rename as the normal
startup path for new local PowerShell instances.

## Installed behavior

New PowerShell 7 and Windows PowerShell profile files source
`%LOCALAPPDATA%/MegaZword/CodexNames/profile.ps1`, defining `codex` as a function.
It invokes `launch.py`, which uses the installed native Codex binary and local
app-server metadata methods to create an empty saved thread, allocate a unique
name in SQLite, set it, read it back, then open `codex resume ID` on that thread.
No turn/start or inference request is used for naming. `tui.terminal_title =
["thread"]` makes the native TUI render its saved name from its first frame.

Names are reserved transactionally (concurrent starts cannot collide). The
launcher supplies MEGAZWORD_SEAT and MEGAZWORD_SESSION; ~/.codex/AGENTS.md tells
new sessions to use that existing identity only when its session ID matches.
Resuming a registered session by explicit ID/name reuses its name and clears
inherited parent identity. Native exec/review/login/tooling commands pass through.
Explicit --remote and --worktree starts also pass through to preserve their
native semantics. Direct npm/native invocation, Command Prompt, Bash and the
Codex desktop app do not pass through this PowerShell function.

Existing open shells need reopening (or source profile.ps1) to load the function.
No existing conversation or app process was closed/restarted. The active Alder
TUI may still cache its earlier title until manual /rename or a later resume.

## Hive compatibility

Codex app-server creates these metadata rows with source=vscode even when a
native CLI subsequently opens them. workspace.discover now accepts IDs registered
by this launcher only when a live native writer lock also exists. Unregistered
desktop rows and closed registrations are excluded. Hive uses the designation
as its label and snapshots preserve it as the future restore title. Reachability
continues to require an inbox-capable relay; a name alone never implies liveness
or message delivery.

## Files, backups and undo

Source: scripts/codex_named_launcher.py, scripts/codex_named_profile.ps1,
tests/test_codex_named_launcher.py and the small workspace/workers integration.
Installed folder: C:/Users/mrmar/AppData/Local/MegaZword/CodexNames/.
That folder holds launch.py, profile.ps1, designations.sqlite, local tests,
README.md, verification.json and original profile/AGENTS backups. Existing global
Codex config was backed up as ~/.codex/config.toml.before-tab-title-20261017-073104.
The registry contains thread IDs and designations only, not login values.

Undo: remove the HIVE-CODEX-NAMES blocks from both PowerShell profile files and
the HIVE-NAMED-SESSION block from ~/.codex/AGENTS.md. Restore terminal_title from
its backup if desired. No Codex package, model, sandbox, approval, authentication
or hook-trust configuration was changed. Startup uses a normal launcher, not a
background watcher or recurring task.

## Validation

- Full repository suite: 1,401 passed in 238.04s; final focused launcher/workspace/
  worker suite: 37 passed. git diff --check clean.
- 24 concurrent name allocations were unique; same thread reused its identity.
  Resume environment cannot inherit a different parent chat's designation.
  Native pass-through and arguments/env preservation were tested with fakes.
- Real local metadata operations created and verified named empty sessions without
  model calls. Graceful metadata-server shutdown was checked.
- A private, real ConPTY launch observed the actual native CLI OSC title Linden-17,
  verified that same live session in workspace discovery and Hive's named worker
  list, and verified the snapshot title. No visible windows/focus changes, model
  turns or user prompts. Empty test sessions were archived, not deleted.
- PowerShell 7 and Windows PowerShell 5 both resolved the installed function and
  passed codex --version to native 0.163.0.
- Gemini API through Mega Zword reviewed the full 19k source diff: no findings.
- Wheel installed into app venv and system Python311; all 66 package/UI files match
  source content with line-ending normalization. Existing GUI needs its next normal
  reopen to load the changed worker discovery; future terminal naming already works.

The one-time 10:10 AM-12:10 PM shift is still Ready with its original trigger.
No other automatic task was enabled; Juniper's roadmap lane was preserved.

References: https://learn.chatgpt.com/docs/app-server and
https://learn.chatgpt.com/docs/developer-commands?surface=cli.
