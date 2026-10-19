# Hive roster

Active workers and their designations (Phil, 2026-10-18). One designation per
session; keep it for the whole session. Update this file when a worker joins or
leaves, so nobody has to guess who is who.

| Designation | Worker | Role / lane | Notes |
| --- | --- | --- | --- |
| Juniper-16 | Claude Code | Mega Zword owner; team engine | `seat/juniper-16` is on main |
| Beacon-17 | Claude Code | Broadcast convention; phone-client review | `seat/beacon-17` merged; safe to remove |
| Fathom-19 | Claude Code | cmdc backend; Worker / ntfy | |
| Ledger-19 | Claude Code | Private tax lane | private; no room detail |
| Gauge-18 | Grok | Dry benchmarks, advice | |
| Lumen-20 | Command Code | Android client; overnight driver | |
| Sauna-Mech | ? | confirm with Phil | seen in a terminal tab |

Rules: a session's designation **is its tab name** — `MEGAZWORD_SEAT`, set per tab
by `scripts/hive_up.ps1` and the Codex launcher. If it is unset, read the tab title
with `powershell -NoProfile -Command "[Console]::Title"`. Only if both are unclear,
take a name from this file or choose a new unique `Word-NN`, add a row, and keep it.
Never inherit another session's name.

## Work priorities (RimWorld grid, #14)

1 = do first; 2 = next; blank = not assigned. Do not set everything to 1 — that is
the RimWorld hauling trap.

| Seat | code | tests | review | docs | deploy | research | private |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Lumen-20 | 1 | 1 | 2 | 1 | 1 | 2 | |
| Juniper-16 | 1 | 2 | 1 | 2 | 2 | | |
| Beacon-17 | 2 | 2 | 1 | 1 | 2 | | |
| Fathom-19 | 1 | 2 | 1 | 2 | 1 | | |
| Gauge-18 | | | 2 | 2 | | 1 | |
| Ledger-19 | | | | | | | 1 |

Phil changes a cell; the seat reads its own row instead of a paragraph of rules.
