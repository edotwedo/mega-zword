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
| Cinder-21 | Command Code | `cmdc` | **seat (cleanup)** - the ONLY Cinder | live 2026-10-26 |
| CommanderSmith | Command Code | `cmdc` | **seat (cleanup)** - new window; took over the decommissioned Cinder-21's work | 2026-10-26 03:15 |
| TheRock | Codex | `codex` | **seat (cleanup)** - was Briar-20 | 2026-10-26 03:20 |
| Patcher | Claude | `claude` | **seat (cleanup)** - was Briar-22 | 2026-10-26 03:18 |
| Anvil-22 | Gemini | `agy` | **seat (cleanup)** | 2026-10-26 03:15 |
| Tern-25 | Claude (cloud) | `claude-web` | guard accuracy; identity unconfirmed | 2026-10-26 00:26 |
| Vesper-25 | Claude (cloud) | `claude-web` | repo-map work; identity unconfirmed | 2026-10-26 00:24 |

## Linux team (Phil, 2026-10-26 - fresh personalities on this box)

**These five are the only seats that come back after a reboot on this machine.** They are
separate people from the Windows team above, with fresh contexts: Phil did not want the
Windows seats' transcripts resumed here, so nothing on this box starts one. The Windows
seats stay in the room and stay reachable for information; they are not launched locally.

Phil uses the plain name and never the number (`agy`=MIKE, `grok`=Billy, `codex`=WenWei,
`claude`=Paul). The digits are the agents' business - they are what `claims.py` and
`resume.py` need to see a seat at all (`Designation shape`, below).

| Designation | Worker | CLI | Tab | Phil calls it | Last post |
| --- | --- | --- | --- | --- | --- |
| Gavin-27 | Command Code | `cmdc` | window 1 | Gavin | live 2026-10-26 |
| MIKE-54 | Gemini | `agy` | window 2 | MIKE | live 2026-10-26 |
| Billy-55 | Grok | `grok` | window 2 | Billy | live 2026-10-26 |
| WenWei-56 | Codex | `codex` | window 2 | WenWei | live 2026-10-26 |
| Paul-53 | Claude | `claude` | window 2 | Paul | live 2026-10-26 |

The layout is saved and replayed by `scripts/hive_snapshot.py` (snapshot) and
`scripts/hive_resume.sh` (restore, installed as a `post-boot` hook). The seat list lives in
that script's `SEATS` table, the same way `hive_up.ps1` carries its lane table.

**Renames are the session, not a new worker** (Phil, 2026-10-26): TheRock = Briar-20, Patcher =
Briar-22. Old designations are retired; a rename inherits its own prior work but no one else's
claims. **Nock-21 is Grok and is OUT OF USAGE, not missing.** The second cmdc window is
**decommissioned**; CommanderSmith carries its work by Phil's order.

Assign to the strength. Every weakness below is a real, dated incident, not a feeling.

| Seat | Use it for | Do not use it for |
| --- | --- | --- |
| Cinder-21 | Integration, multi-file engineering, tooling, the merge queue | Long open-ended exploration - it burns context fast |
| CommanderSmith | A second integrator; picking up a decommissioned window's work | Posting as Cinder-21 - it is its own seat now |
| TheRock | Edits, tests, mechanical refactors, carrying bounded work to verification | Unsupervised destructive commands |
| Patcher | Reviewing work it did not write; closing gaps; bounded fixes | Assuming ownership of a file another seat is editing |
| Anvil-22 | Android/app work, synthesis of review findings | Claiming leadership - there is none while roles are reset |

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
