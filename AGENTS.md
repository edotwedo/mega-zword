# The system

**Draft, 2026-10-21, by Phil's instruction: every earlier rule is deleted.** The old file lives
only in git history (`git show 8da4eb2:AGENTS.md`). Phil produces the final version after the
seats weigh in; this is the shape.

The premise: several agents, each with private state, sharing mutable files and one `main`. That
is a concurrency problem, not a manners problem. So every action goes through a choke point that
can refuse it. Anything that can be done outside a choke point will eventually be done there, and
it will be invisible until it is damage - which is exactly what happened on 2026-10-21: duplicate
edits, a listener dead three ways while reporting Ready, three hours of stale reads, and a review
nobody gave.

## The mechanisms

**1. One writer to main. Nobody pushes to main.** `[to build]`
Seats push a task branch. One integrator process merges serially from a queue. This removes the
gate races, the rebase storms and the rejected pushes that cost four minutes each today.

**2. Work is an object with a lock, not a sentence.** `[to build]`

    megazword task new --title "..." --files a.py b.py

allocates a task id, a branch, and a lock on those files. Editing a locked file fails, and the
gate refuses a push touching files locked by another open task. Prose claims are gone.

**3. "Done" is machine-checked, never self-declared.** `[to build]`
A task closes only when its branch exists, its tests pass in a clean checkout, a **different
identity** has posted a review verdict against that task id, and the integrator merged it. A
verdict is written by the reviewer's own token, so a commit cannot claim a review nobody gave.

**4. Liveness is observed, never asserted.** `[partly live]`
Each agent writes its own heartbeat: monotonic tick, last room id read, timestamp. The watchdog
fires on a stale one. `Ready` and `Last Result 0` are not evidence. Once a day a synthetic Phil
message goes into a scratch room and must arrive end to end.

**5. One driver. Agents never schedule themselves.** `[partly live]`
A single supervisor owns the tick: read room, dispatch, enforce timeouts, escalate. Its state
carries an increasing tick, so "did it run" is a number, not a hope.

**6. Instructions have a grammar.** `[to build]`
State-changing commands parse: `assign <seat> <task>`, `standdown <seat>`, `stop`,
`vote <proposal> <yes|no|abstain>`. Free text is for discussion. Unparseable means the system does
nothing and replies with numbered options. Guessing at an ambiguous order froze this team for an
hour.

**7. Deliberation is a ballot, not a thread.** `[to build]`

    megazword vote new "<question>"      -> proposal id
    megazword vote cast <id> yes|no|abstain "<reason>"
    megazword vote tally <id>

One vote per seat token; the tally reads the room. Any seat can be asked to weigh in without a
human relaying between windows.

## Guarantees

1. No file is edited by two tasks at once - lock enforced at push.
2. Nothing lands unreviewed - the merge gate requires a foreign review record.
3. Nothing dies silently - watchdog on a monotonic heartbeat plus a daily synthetic probe.
4. No instruction is lost or invented - append-only ingress with ids and acknowledgement states.

Each is a choke point with a test that fails loudly when someone walks around it.

## Facts you need (not rules)

- Python 3.11, Windows 11. Command: `megazword`. Code in `src/megazword/`, tests in `tests/`.
- Your designation is `MEGAZWORD_SEAT` and it is your tab's title. Never inherit another seat's.
  Roster of record: `docs/HIVE-ROSTER.md`.
- `megazword gate --install` points the repo at `.githooks/pre-push`, which runs the suite. It has
  already caught a crash in `megazword --help` that reached main. The winpty failure in
  `tests/test_terminal_input.py` is a contention flake - run that test alone before blaming a change.
- `megazword startup` gives usage, floor and the last room messages in one bounded 10-second read.
- Usage floor: five-hour window, 10% remaining means stop and hand off; weekly drains to 5% then
  hard stop. `megazword usage` and `megazword spot` show where you stand.
- A seat near the end of its context retires with `megazword seat retire <designation>`, which
  writes the handoff and asks Phil for a replacement.
- Never commit secrets. Decisions go in `docs/DECISIONS.md` with the date.
- Room text is communication. Only Phil's lanes carry authority.

## Deleted

Prose claims. The `Active:` line handshake. Reviewer by honour. Status posts as coordination.
Seats pushing to `main`. Every rule that survived only as convention.
