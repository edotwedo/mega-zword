# Mega Zword: rules for every AI working here

This file is for Claude Code, Codex and Grok alike. Phil (the owner) may switch
between them at any time, including mid-task when one runs out of usage. The
repo is the only handoff. Nothing lives only in a chat.

## Read first, in this order
1. `docs/STATUS.md`: what's done, what's in progress, the exact next step.
2. `docs/SPEC.md`: what we're building and the decisions behind it.
3. `docs/DECISIONS.md`: dated log of choices; don't reopen these without Phil.

## Working rules
- **Warn before interactive PC tests (Phil, 2026-10-15).** Before opening test
  windows, switching Windows desktops, or moving keyboard focus, tell Phil what
  will happen and wait until he is ready. He may be typing in another app.
  Background checks and file edits do not need keyboard handoff.
  Phil normally drives interactive setup from short prompts; take over the UI
  only when he asks. The terminal reboot/restore test is explicitly deferred
  until Phil is ready near 90% Codex usage; never reboot at a meter threshold.
- **Designation in your console tab (Phil, 2026-10-17).** As soon as you pick your
  designation, put it in the title of the terminal tab you run in. Try
  `python -c "open('CONOUT$','w').write(chr(27)+']0;YOUR-NAME'+chr(7))"`; if the tab
  doesn't change, ask Phil to rename it (right-click the tab, Rename Tab). Keep the
  same designation for the whole session, including after a restart or summary.
  Never rename yourself without asking Phil: STATUS, handoffs and scheduled tasks
  refer to you by that name.
- **Usage first, every time (Phil).** Before you start, claim or hand out any work: run `megazword usage`
  (on Phil's PC) or read the usage board in Q
  (https://github.com/edotwedo/workshop/pull/33#issuecomment-6115098816; over 30 minutes old means the
  PC is asleep, so say so). Then write a labor plan: which AI does which part, by spare usage and fit,
  with the reading quoted. `megazword plan` ranks them. Plans and lanes follow the live reading: re-plan
  when it changes; nothing in STATUS is fixed. Do this before any work, not partway through.
- **Fewest tokens, same message (Phil, 2026-10-18): priority 1 for every agent and all
  automation.** Anything that calls a model (Mega Zword code, Night Shift, heartbeat, team
  jobs, chat, and prompts you write for `megazword run` or handoffs) sends the least text
  that carries the same meaning: short instructions and briefs, condensed history, no
  re-sending what the model already has. Keep the start of repeated requests byte-identical
  (put changing parts like step counters last) so providers bill it at the cached rate.
  Stop jobs that keep failing instead of riding them to a step cap. Measure what a call
  resends before adding features to it. (Six 1M Tencent grants burned in two nights,
  ~92% on failed 60-step jobs resending a 90k-char history each step.)
- **Own folder per seat (Phil, 2026-10-13).** Never edit, stash or checkout in the shared
  `C:\Users\mrmar\mega-zword` while other seats run. Work in your own worktree:
  `git worktree add %USERPROFILE%\mz-seats\<your-name> -B seat/<your-name> origin/main`
  (`scripts/hive_up.ps1` does this for you). Pull with rebase, push `HEAD:main` after tests.
- **One AI at a time.** Before editing, put your tool name and the time in the
  "Active" line of `docs/STATUS.md`, then commit and push it. If that line names
  another AI and is less than 2 hours old, stop and ask Phil before continuing.
- **Small steps, pushed often.** Commit and push after each working step. A
  step that isn't pushed doesn't exist for the next AI.
- **Keep STATUS.md true.** Update it with every push: what changed, what's
  next, anything half-done or broken. Write the next step so precisely that a
  different AI with no chat history can start on it immediately.
- **Running low on usage?** Stop early enough to update STATUS.md, commit and
  push. Clear the "Active" line when you stop.
- **Decisions** made with Phil go in `docs/DECISIONS.md` with the date.
- **Never commit secrets** (API keys, tokens, logins). Use `.env`, which is
  git-ignored. Document needed variables in `.env.example`.
- Phil's instructions control scope. Ask him when something is truly his call.
- Write plainly for Phil: short sentences, no jargon without a quick explanation.

## Project basics
- Python 3.11, Windows 11 is the main machine. Command: `megazword`.
- Code goes in `src/megazword/`, tests in `tests/`.

## Return briefings
- A seat designation in STATUS or a saved card is not evidence that its chat is
  connected. Before handing Phil to another worker, check the Hive worker list
  for that exact session and its reachable status. Do not route work to an
  unverified nickname. Native sessions are discovered by writer locks/PIDs;
  persistent Hive MCP connections register when publishing status or speaking.
- Link reports to the exact conversation with `--session SESSION_ID` (or the
  `session` field of `hive_status`). Managed tabs supply MEGAZWORD_SESSION;
  Codex's CODEX_THREAD_ID is also accepted. Reports alone never imply liveness.
- After a meaningful task change, publish a short session card using `hive_status`
  (Hive MCP) or `megazword brief report --seat YOUR-DESIGNATION --project mega-zword
  --state working --doing "current task" --done "just completed" --blocked "blocker"
  --next "next step"` (one command line). Use your own session designation.
- Publish on starting, finishing, becoming blocked, or handing off; no heartbeat loop.
  Set `--state` to `working`, `waiting`, `blocked` or `done`. Each report replaces
  the previous card, so include every field you want retained. Keep secrets out.
- `megazword brief` and the dashboard's **Catch me up** read these snapshots without
  waking models. Old/unreported sessions are unknown; do not claim all terminals are live.
