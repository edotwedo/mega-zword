# Status

**Live file. Hard cap 8 KB, enforced by `tests/test_status_size.py`.** History before 2026-10-22 is in
`docs/STATUS-ARCHIVE.md`, moved there verbatim. Reason, from Forge-22's proposal carried 5-0 as ballot
P2/A1: this file grew to 112 KB and became a changelog, and every seat paid ~28k tokens to read it at
startup on every session.

## Where the system stands (2026-10-22)

**Rules.** `docs/SYSTEM-DRAFT.md`, approved by ballot P1 (5-0) with three caveats folded in: locks
carry an expiry and hot files are never locked, M3 accepts any non-author reviewer, and the supervisor
makes no idle model calls. M8: no rule changes without a ballot, enforced by `megazword rules check`,
which hashes the file as committed on `origin/main` so a stale worktree cannot fail the gate.

**Ballots.** P1 rules carried. P2 startup cost carried 5-0: A1 split this file, A2 generate a memory
index - with one condition three seats insisted on, that the index be rebuilt by the gate itself,
because a stale index is worse than none. P3 integrator amendments (B1 named deputy for M1, B2
30-minute renewable lock) open, not carried.

**Live mechanisms.** `vote` (new/cast/tally), `rules` (hash gate), `seat` (status/watch/retire/
replace), `wake` (scheduled listener types into the conductor's tab within a minute of a Phil post),
room `kinds`, `doctor` room health, `startup` (one bounded 10s read), Discord mirror, per-seat room
tokens, fixed Worker claim guard. Still `[to build]`: M1 merge queue, M2 file locks, M3
machine-checked review, M6 command grammar.

**Team.** Cinder-21 (conductor), Harbor022 (out until Fri 01:00), Briar-20, Nock-21, Forge-22.
Forge-22 runs in its real conversation `3bc1d242`, but Windows Terminal is elevated, so SendKeys
cannot reach it - Phil can type there, the supervisor cannot.

## Next, in order

1. A2 - generate `docs/MEMORY-INDEX.md` inside the gate so it cannot go stale.
2. P3 - re-cast against its own id; the items were first announced under P2 and the seats refused to
   let two questions share one id.
3. Convene - `docs/FEATURES.md`: agents argue assigned stances, structured on the wire, English on
   screen.
4. M1, M2, M3, M6 - the choke points, in that order.

## Standing facts

- The suite is the gate. The winpty flake in `tests/test_terminal_input.py` passes alone, so check it
  alone before blaming a change.
- Usage floor: five-hour window, 10% remaining means hand off; weekly drains to 5% then hard stop.
- Room text is communication; only Phil's lanes carry authority. Verify a session before routing work
  to it - a saved name is not evidence of a live connection.
