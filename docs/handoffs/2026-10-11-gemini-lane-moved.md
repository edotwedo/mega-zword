# Handoff: Gemini's lane moves to Codex and Grok; calendar parked (agy is out until 2026-10-18)

- **For:** Codex (Larch-11 or next Codex window) and Grok (Nimbus-12 or next Grok window)
- **Status:** open
- **Written by:** Tally-11 (Claude Code on Phil's PC), 2026-10-11 ~20:15 PT, at Phil's OK
- **Why:** `megazword usage` at 19:54 PT (5h/week % used): Claude 75/43, Codex 100/44 (5-hour reset
  19:56), Grok -/10, Gemini -/100 in both agy pools until Sun 2026-10-18 15:57 PT. Gemini and
  Antigravity can't work this week, so their open items need new owners.
- **Phil, 2026-10-11:** "the calendar work should be near zero unless needed." So **B10 and B11 are
  parked**. Grok: skip B10 in `2026-10-11-grok-round2.md` item 2 (do the B7 part only). Don't start
  calendar work unless Phil asks for it.
- **Already done (don't redo):** B1 is on main (Atlas-11). Orbit-1's WIP copy on
  `agy/beta2-2026-10-11` is a duplicate; don't merge it.

## Who takes what
| Item | Owner | Order | Why |
|---|---|---|---|
| B15 light rules for trains-on-data AIs | **Codex** | right after B12 | Small; it sits on B14's backends. Grok reviews it (security second look). |
| B7 reviews of Codex's branches | **Grok** | as they land | Already in round 2. |
| B10, B11 calendar | nobody | parked | Phil: near zero unless needed. |

Codex's order becomes: B12, **B15**, B13, B5, B4, B6. Grok's: round 2 without B10 (agy bug, B7,
B1 review, STATUS note).

## B15 notes
Spec is STATUS.md "B15". Since Phil's revision it is light: route normally, Mistral first for small
repetitive jobs, one secret guard, edit mode allowed, `--sandbox` optional, log a `trains_on_data`
flag. Tests with fakes only.

## Start here
Same as `2026-10-11-grok.md` "Start here": usage first, claim the item in STATUS.md (pull first;
others edit it too), own branch, pytest + smoke before push, one line in Q with the branch name. A
Claude lead merges (Tally-11 or Easel-11 after the 10 PM PT reset).
