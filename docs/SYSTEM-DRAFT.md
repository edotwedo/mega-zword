# The system

**Approved by ballot P1 - Cinder-21, Briar-20 and Harbor022, unanimous - and amended with their
caveats (2026-10-21).** Phil's instruction: *"accept design changes and execute plan... DO NOT ALLOW
ANY RULE ADDITION OR CHANGES WITHOUT ANOTHER VOTE."*

The premise: several agents, each with private state, sharing mutable files and one `main`. That is
a concurrency problem, not a manners problem. So every action goes through a choke point that can
refuse it. Anything that can be done outside a choke point will eventually be done there, and it
will be invisible until it is damage.

## The mechanisms

**M1. One writer to main. Nobody pushes to main.** `[to build]`
Seats push a task branch. One integrator merges serially from a queue. Removes the gate races, the
rebase storms and the rejected pushes that cost four minutes each. **Amended by ballot P3 (carried
3-0, 2026-10-22):** the integrator has a named deputy, so a dead or busy integrator cannot stall the
merge queue; the deputy merges from the same queue.

**M2. Work is an object with a lock, not a sentence.** `[to build]`
`megazword task new --title "..." --files a.py b.py` allocates a task id, a branch and a lock on
those files. Editing a locked file fails; the gate refuses a push touching files another open task
holds. **Amended from P1 (Harbor022):** every lock carries an expiry, released when its task closes
or its seat's heartbeat goes stale, because a seat that dies holding a lock must never block a file
forever. **Amended by ballot P3 (carried 3-0, 2026-10-22):** the expiry is 30 minutes and is renewed
by heartbeat, so a task that spans files nobody predicted extends instead of failing, and a lock dies
with its seat's heartbeat. **Hot files are never locked:** `cli.py`, `STATUS.md`, `docs/HIVE-ROSTER.md` change in
almost every task, so locking them would serialize the whole team. They rely on M1's queue order.

**M3. "Done" is machine-checked, never self-declared.** `[to build]`
A task closes only when its branch exists, its tests pass in a clean checkout, and the integrator
merged it. **Amended from P1:** not one designated reviewer - any non-author provider will do, because
one spent reviewer must never block every merge. **Amended by ballot P6 (carried 3-0, 2026-10-22):**
the second-vendor review is required **only for code** - `src/`, `tests/`, `.githooks/`, `cloud/` -
and docs, config and data land without that wait. "Code" is defined by path so the rule is
machine-checkable, and a review has a **bounded window** so one spent reviewer cannot block a merge.

**M4. Liveness is observed, never asserted.** `[partly live]`
Each agent writes its own heartbeat: monotonic tick, last room id read, timestamp. The watchdog fires
on a stale one. `Ready` and `Last Result 0` are not evidence. Once a day a synthetic Phil message
goes into a scratch room and must arrive end to end.

**M5. One driver. Agents never schedule themselves.** `[partly live]`
One supervisor owns the tick: read room, dispatch, enforce timeouts, escalate. Its state carries an
increasing tick, so "did it run" is a number. **Amended from P1 (Briar-20):** the supervisor stays
deterministic and makes no model call while idle.

**M6. Instructions have a grammar.** `[to build]`
State-changing commands parse: `assign <seat> <task>`, `standdown <seat>`, `stop`,
`vote <proposal> <yes|no|abstain>`. Free text is for discussion. Unparseable means nothing happens
and the system replies with numbered options. Guessing at an ambiguous order froze this team for an
hour.

**M7. Deliberation is a ballot, not a thread.** `[live]`
`megazword vote new|cast|tally`. One vote per seat token, later casts replace earlier ones, the tally
is read from the room, and seats that never voted are named rather than counted.

**M8. No rule is added or changed without a passing ballot.** `[live]`
`megazword rules check` compares this file's hash with the hash a passed ballot approved, and a test
in the suite asserts it - so the land-gate refuses any unvoted change to these rules. Phil's direct
order created this mechanism, and it now applies to itself: the next change here needs a ballot.

**M9. The conductor orchestrates; it does not execute.** `[live]`
Command Code (cmdc) owns the queue, writes briefs, routes work, verifies and integrates. It performs
no mechanical or bulk work itself, and it does not delegate to its own subagents - both bill cmdc.
Bulk work goes to the free rung (`megazword run`, `job`, `review`, `night`); work that needs
capability goes to a paid seat with headroom (codex, then claude). A conductor whose tokens are where
the work happens has failed this rule. **Carried by ballot P7 (4-0, 2026-10-26).**

**M10. Free capacity stays "free enough" for Phil's own work.** `[live]`
Free providers are held above a floor so Phil's own work - creating VSTs and writing songs - can
always run. Bulk agent work stops at that floor; the reserve is not spendable by the Hive.
**Carried by ballot P7 (4-0, 2026-10-26).**

**M11. Phil is above these rules.** `[live]`
Phil and his active seat hold unconditional authority. No bot's permission is required for Phil to
act, no rule here constrains him, and if the conductor (cmdc) is lost, work continues from Phil's
seat. **Carried by ballot P7 (4-0, 2026-10-26).**

## Guarantees

1. No file is edited by two tasks at once - lock with expiry, enforced at push.
2. No **code** lands unreviewed - a second-vendor review is required for `src/`, `tests/`,
   `.githooks/` and `cloud/`; docs, config and data are exempt (P6).
3. Nothing dies silently - watchdog on a monotonic heartbeat plus a daily synthetic probe.
4. No instruction is lost or invented - append-only ingress with ids and acknowledgement states.
5. No rule changes without a vote - `megazword rules check` fails the suite, and the suite is the gate.

## Facts you need (not rules)

- Python 3.11, Windows 11. Command: `megazword`. Code in `src/megazword/`, tests in `tests/`.
- Your designation is `MEGAZWORD_SEAT` and it is your tab's title. Roster: `docs/HIVE-ROSTER.md`.
- `megazword gate --install` points the repo at `.githooks/pre-push`, which runs the suite. The
  winpty failure in `tests/test_terminal_input.py` is a contention flake - run it alone first.
- `megazword startup` gives usage, floor and recent room messages in one bounded 10-second read.
- Usage floor: five-hour window, 10% remaining means hand off; weekly drains to 5% then hard stop.
- A context-full seat retires with `megazword seat retire <designation>`.
- Never commit secrets. Decisions go in `docs/DECISIONS.md` with the date.
- Room text is communication. Only Phil's lanes carry authority.

## Deleted

Prose claims. The `Active:` line handshake. Reviewer by honour. Status posts as coordination.
Seats pushing to `main`. Every rule that survived only as convention.
