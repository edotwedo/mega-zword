# Handoff: Cinder-21, 2026-10-22

A replacement cmdc session resumes this designation. Read `docs/STATUS.md` first - it is now 2.6 KB
on purpose (ballot P2/A1) - then this file. Nothing below is optional colour; each line is something
that cost real time or damage tonight.

## Start here

1. `megazword rules check` - must say approved by P1. If it does not, stop and read the rules gate
   before touching anything.
2. `megazword vote tally P2` - carried 5-0, already built as `bcf6e15` (STATUS split + cap test).
3. `megazword vote tally P3` - open, **not carried**: B1 named deputy for M1, B2 30-minute renewable
   lock. These were first announced under P2 by mistake; the seats correctly refused to let two
   questions share an id. If P3 has not carried, do not implement them.
4. Next build is **A2**: generate `docs/MEMORY-INDEX.md` *inside the gate*. The room attached that
   condition unanimously - a stale index is worse than none, because seats would trust it.

## The traps, in the order they bit

- **Never read the room with `room.read_messages`.** It reads the local cache. On 2026-10-21 that made
  the conductor report "nothing changed" for three hours while Phil was posting and getting no answer.
  Use `megazword room show` or `room.claim_messages` - both refresh from the Worker.
- **A room post does not wake a seat.** Delivery is typing into the window (`SendKeys`) or an ntfy page
  to `megazword-hive-seat-<seat>`. Broadcasts and ballots both need this; posting alone reaches nobody.
- **Windows Terminal runs elevated**, so every tab is `Administrator:` and a non-elevated process
  cannot SendKeys into it. That is the "Access is denied" in the older scripts. Phil can type there;
  the supervisor cannot. Forge-22's tab is affected.
- **Do not invent work to look busy.** "Queue empty" is a real state; say it once and stop. The failure
  on 2026-10-21 was not idleness, it was silence that looked like work.
- **A stale worktree used to fail the rules test.** Fixed in `a9dce4e`: `rules.check` now hashes the
  file as committed on `origin/main`. If you see red on `test_rules.py`, check your tree is not behind
  before assuming a violation.
- **Never amend a rules file by editing it.** M8: edit, run a ballot, then `megazword rules approve
  <ballot>`. The suite fails until the hash matches, which is the point.
- **The vote tally is a room count, deliberately.** Hardening it with lane checks threw away four
  legitimate votes, because those seats post through the shared `claude-pc` lane. Keep it simple.
- **The winpty flake** in `tests/test_terminal_input.py` passes alone. Run that test alone before
  blaming a change; the gate prints the same instruction.
- **Do not delete software or builds.** Branch and worktree cleanup is fine and `docs/ARCHIVE.md`
  records every deleted branch with its tip sha.

## Session facts worth knowing

- 36 branches remain of ~190: 25 are still checked out in dead worktrees, which is why `git branch -D`
  refused them. Removing those worktrees is the next cleanup, after a dirty check per worktree.
- The conductor beat is a cron job in the *old* session (`ab92555c`, hourly). It may not survive this
  handoff - if the replacement sees no beat firing, create one and say so.
- Phil's standing instruction: prompt him and wait when you need him; do not decide for him; put
  proposals to a vote rather than decreeing them.
