# Handoff: Mega Zword lead seat (from Tally-11)

- **For:** the next Claude lead, in a new chat (Phil is starting one because Tally-11's chat is full)
- **Status:** open
- **Written by:** Tally-11 (Claude cloud chat), 2026-10-12 ~13:00 PT
- **Pick your own designation.** Don't sign as Tally-11 or Kestrel. A PC Claude also signed "Tally-11"
  earlier, which confused Q.

## Your job
Lead = review and merge finished branches, keep STATUS.md true, re-plan the lanes by live usage.
Claude has the tightest usage, so you don't build. Hand building to whoever has the most room.

## First, every time (Phil's rule, not optional)
1. Read usage before any work: `megazword plan` and `megazword usage` on the PC, or the Q usage board
   (https://github.com/edotwedo/workshop/pull/33#issuecomment-6115098816).
2. Write a labor plan from that reading, with the numbers quoted. Lanes are a starting point, not a rule;
   re-plan when the reading changes (DECISIONS 2026-10-12).
3. The Q board has been stale since **Sun Oct 11 4:27 PM** (the PC task isn't installed yet). Say so, and
   use the newest reading in STATUS.md until Phil runs the installer below.

Last reading (Larch-11, STATUS, Oct 12 04:48 PT), weekly used: Grok 15%, Claude 54%, Codex 57%,
Gemini 100% until Oct 18.

## Where Beta 2 stands
- Done and on main: room engine (B1), lessons and summaries (B2), tabs backend (B3), Hive screen (B4),
  chat tabs UI (B4b), new look (B5), app header and guide (B6), desktop window and Start menu (B6b),
  Sentinel (B8/B9), per-task model choice (B12), plain `megazword` opens the app (B13), free AIs (B14),
  rules for AIs that train on our data (B15), `megazword plan` and the usage hook.
- Open:
  - Codex: tab order (claimed in the Active line), then the B6 standalone .exe.
  - Grok (most room): B10/B11 Google Calendar (moved from Gemini, who is out) and fixing the 3 Windows-only
    tests that fail on Linux: `tests/test_no_real_cli.py::test_a_cli_outside_the_repo_and_temp_is_refused`
    and 2 install tests in `tests/test_sentinel.py`. They likely turn CI's Ubuntu job red.
  - B7 reviews (Grok) as items land.
- Tests on main (cloud, Linux): 673 passed, 3 failed (above), 1 skipped.

## Phil to-dos (remind him once, don't nag)
In `C:\Users\mrmar\mega-zword` on his PC:
1. `git pull`, then `python scripts\install_usage_hook.py --yes`. This adds the usage hook to his user
   Claude settings and schedules the Q usage board refresh every 15 minutes. The safety classifier
   blocked doing this automatically from the repo hook, so it's his explicit command.
2. Optional: `megazword sentinel install --yes`, plus the ntfy app on his phone.
3. Start Grok on the re-plan items.

## Things that bit us (don't repeat)
- **Usage check skipped.** Phil had to ask several times. Do it first, always.
- **Static lanes.** Phil rejected "frozen lanes"; plans follow usage.
- **Grok marked out by mistake.** Oct 17/18 is its weekly *reset*, not an out date. If Mega Zword shows
  Grok out, check `megazword out grok --clear` with Phil.
- **Wrong install folder.** Phil's real checkout is `C:\Users\mrmar\mega-zword`; the `mz-*` folders are
  old worktrees, safe to remove.
- **Shared branch.** The workshop branch `robotronc/determined-tesla-v0v7e6` was used by two sessions.
  Check `git log origin/<branch>` before pushing; never force over someone's commits.
- **Cloud can't reach Phil's PC.** Anything needing his PC is a short command for him, or work for a
  Claude/Codex running on the PC.

## Where things are
- Mega Zword state: `docs/STATUS.md` (top lines, lanes, Done), `docs/SPEC.md` "Beta 2", `docs/DECISIONS.md`.
- Hive state: workshop `AGENTS.md`, `DECISIONS.md`, `TEAM.md`, Q (workshop PR #33).
- Usage tooling: `megazword plan`, `megazword usage`, `.claude/hooks/usage_check.py`,
  `scripts/install_usage_hook.py`, `scripts/publish_usage.py`.
