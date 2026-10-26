# Hive roster

Active workers and their designations. One designation per session; keep it for the
whole session. Update this file when a worker joins or leaves, so nobody has to guess
who is who. **Roster edits are the conductor's alone** (Forge-22, Phil 2026-10-23): a
seat never adds, renames or retires itself.

**Ownership is RESET (Phil, 2026-10-25): no seat is Lead Conductor or overall owner while the cleanup runs. Phil owns. Every live seat works the cleanup; roles and leadership are re-decided after it.**
Phil overrules previous conductor designations and bureaucratic voting deadlocks.
Seats support Phil's verified active lead. Reviews are advisory sanity checks ("another set of eyes")
before commit, NOT parliamentary merge-blocking voting stalls.

## Active team (Phil, 2026-10-26 - measured from the room, not asserted)

One live window per paid solution. This is the entire team; there is no second stream.

| Designation | Worker | CLI | Role | Last post |
| --- | --- | --- | --- | --- |
| Cinder-21 | Command Code | `cmdc` | **seat (cleanup)** | live 2026-10-26 03:04 |
| Briar-20 | Codex | `codex` | **seat (cleanup)** | live 2026-10-26 03:06 |
| Briar-22 | Claude (`claude-pc` lane) | `claude` | **seat (cleanup)** | live 2026-10-26 03:08 |

Assign to the strength. Every weakness below is a real, dated incident, not a feeling.

| Seat | Use it for | Do not use it for |
| --- | --- | --- |
| Cinder-21 | Integration, multi-file engineering, tooling, the merge queue | Long open-ended exploration - it burns context fast |
| Briar-20 | Edits, tests, docs, mechanical refactors, sandboxed runs | Unsupervised destructive commands; scope it explicitly |
| Briar-22 | Breadth, a second reading, review of work it did not write | Assuming it owns a file another seat is editing |

**Designation shape:** `[A-Za-z]{3,}-?\d{1,4}` - so `Harbor022` is as valid as `Cinder-21`.
`claims.py` (`PREFIX`) and `resume.py` (`ROW`) must both accept it. A designation that does
not parse makes the seat invisible to `megazword resume` and stops its claims registering.

## Retired (history - do not reuse these names)

### Lost contact, 2026-10-26 (no post for 12h+; removed from the active team)

Measured from the room, not from anyone's word. Claims released; nothing waits on them.

| Designation | Last post | Why it was removed |
| --- | --- | --- |
| Nock-21 | 2026-10-25 15:24 (11.8h) | no contact |
| Anvil-22 | 2026-10-25 02:42 (24.5h) | no contact |
| Harbor022 | 2026-10-25 00:03 (27.2h) | no contact; had been rostered "out until Fri" for four days |
| Forge-22 | 2026-10-24 02:00 (49.2h) | no contact; was the designated **Lead Conductor** and had been dark the whole time - the reason roles are not prose any more |


Kept so nobody has to guess why a familiar name is missing.

| Designation | Why it stopped |
| --- | --- |
| Juniper-16 | Superseded by the five-seat team, 2026-10-21 |
| Beacon-17 | Superseded by the five-seat team, 2026-10-21 (`seat/beacon-17` was merged) |
| Fathom-19 | Superseded by the five-seat team, 2026-10-21 |
| Ledger-19 | Superseded by the five-seat team, 2026-10-21 (private tax lane, no room detail) |
| Gauge-18 | Superseded by the five-seat team, 2026-10-21 |
| Lumen-20 | Superseded by the five-seat team, 2026-10-21 |
| Quill-21 | Superseded by the five-seat team, 2026-10-21 |
| Word-28 | Superseded by the five-seat team, 2026-10-21 |
| Sauna-Mech | Name never confirmed with Phil; retired 2026-10-21 |

## Work priorities (RimWorld grid, #14)

1 = do first; 2 = next; blank = not assigned. Do not set everything to 1 - that is the
RimWorld hauling trap. Harbor022's row is deliberately thin: it is the seat with 5% of
its window left above the reserve.

| Seat | code | tests | review | docs | deploy | research | private |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Cinder-21 | 1 | 1 | 2 | 2 | 2 | | |
| Harbor022 | | | 1 | 2 | | 2 | |
| Briar-20 | 1 | 1 | 2 | 1 | 1 | | |
| Nock-21 | 2 | 2 | 1 | 2 | | 1 | |
| Forge-22 | | | 2 | | | 1 | |

Phil changes a cell; the seat reads its own row instead of a paragraph of rules.

## How a designation is set

A session's designation **is its tab name** - `MEGAZWORD_SEAT`, set per tab by
`scripts/hive_up.ps1` and `scripts/hive_resume.ps1`. If it is unset, read the tab title
with `powershell -NoProfile -Command "[Console]::Title"`. Only if both are unclear, ask
the conductor for a name and add a row. Never inherit another session's designation, and
never rename yourself to a different name than your roster row.
