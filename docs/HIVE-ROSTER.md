# Hive roster

Active workers and their designations. One designation per session; keep it for the
whole session. Update this file when a worker joins or leaves, so nobody has to guess
who is who. **Roster edits are the conductor's alone** (Cinder-21, Phil 2026-10-21): a
seat never adds, renames or retires itself.

**Overall owner: Command Code (cmdc), by Phil's direct decision 2026-10-20.**
Other seats support its verified active lead. Usage rankings choose support,
not ownership. See `CMDC-OWNERSHIP.md`; confirm the exact lead session before
handing off. Provider availability is not worker liveness.

## Active team (Phil, 2026-10-21)

One live window per paid solution. This is the entire team; there is no second stream.

| Designation | Worker | CLI | Role | Window (read 2026-10-21) |
| --- | --- | --- | --- | --- |
| Cinder-21 | Command Code | `cmdc` | **Conductor - holds the queue, assigns, owns integration** | 72% left (5h 10% used, week 28% used) |
| Harbor022 | Claude Code | `claude` | Design, decisions, review | **OUT until Fri 01:00 (Phil, 2026-10-21)** - he stopped Claude early at 75% weekly. Finishing its in-flight audits, then no further assignments |
| Briar-20 | Codex | `codex` | Mechanical edits, tests, docs, sandboxed runs | 83% left (5h 15% used, week 17% used) |
| Nock-21 | Grok | `grok` | Breadth, critique, benchmarks, cheap volume | 71% left (week 29% used) |
| Forge-22 | Gemini | `agy` | Second opinion; access moves to the Discord mirror when its window resets | own week 17% used, but its Claude/GPT models are 100% used until Tue 09:09 PM |

Assign to the strength. Every weakness below is a real, dated incident, not a feeling.

| Seat | Use it for | Do not use it for |
| --- | --- | --- |
| Cinder-21 | Conductor work, integration, multi-file engineering, tooling | Long open-ended exploration - it burns context fast and it is the conductor |
| Harbor022 | Decisions, design, review of high-risk changes, cross-checking | Volume, bulk edits, anything a seat with more room can do |
| Briar-20 | Edits, tests, docs, mechanical refactors, sandboxed runs | Unsupervised destructive commands; scope it explicitly or it edits outside the ask |
| Nock-21 | Breadth, critique, a second reading, benchmarks | Anything scripted or automated: xAI's AUP names automated access as a risk (`docs/PROVIDER-TERMS.md`) |
| Forge-22 | A second opinion when its models have room | Background or bulk work; it burns a window fast and is already spent |

**Designation shape:** `[A-Za-z]{3,}-?\d{1,4}` - so `Harbor022` is as valid as `Cinder-21`.
`claims.py` (`PREFIX`) and `resume.py` (`ROW`) must both accept it. A designation that does
not parse makes the seat invisible to `megazword resume` and stops its claims registering.

## Retired (history - do not reuse these names)

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
