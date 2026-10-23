# ROADMAP (draft, not approved): seats keep their identity when the model changes

Author: Forge-22, from Phil's brainstorm 2026-10-22. DRAFT. Nothing here is built, and nothing is a
rule until a ballot passes (M8).

## What Phil asked for
- A seat keeps **one stable name** ("him") across a model switch. It does not need its full context
  or to behave identically. It needs to **continue the work** and be referred to the same way.
- **One live seat per designation.** If the chat room needs forwarding to make that true, that is an
  implementation detail Phil does not need drawn out.
- **Only the CLI reports usage.** If a model switch happens inside a session, the CLI still gives the
  numbers. The switch is a **tool call**, not a human step.
- Goal: no hands-on babysitting when a provider's quota runs out.

## Principle
A designation names a **slot**, not a model. The model is an attribute of the slot and can change.
Identity = designation + a short handoff packet. Context is not carried over.

## Phase 0. Facts first (spike, nothing built)
Answer by reading the CLI docs and trying it; do not guess.
1. Can the CLI change its model from a tool call or command, inside a running session? Exact slash
   command syntax and the exact model names it accepts. Does typing it via the terminal-input path work,
   and does the usage report change afterwards? Do the models share one quota or have separate pools
   (if shared, switching between them avoids nothing)?
2. Can the CLI report usage and the active model in a machine-readable form?
3. If either is no: what is the smallest wrapper that gets the same result (close and respawn with a
   `--model` flag and the same tab title)?
4. Does the quota the CLI reports match the model actually running? (We found a seat labelled Gemini
   while the selected model was Claude.)
Done when: a one-page answer with commands that were actually run. Output decides Phases 3 and 4.

## Phase 1. Identity as a slot (needs ballot: changes roster meaning)
- Roster row per designation: `designation, model, provider, tab title, generation, handoff path, status`.
- `generation` increments on every switch so "which incarnation wrote this" is answerable.
- One live seat per designation, enforced by a lock like M2's (expiry, heartbeat-renewed). A second
  seat claiming a held designation is refused.
- Room posts, claims and ballot votes stay keyed by designation, so nothing downstream changes.
Done when: roster schema + duplicate-designation refusal + tests; existing seats load unchanged.

## Phase 2. Minimal handoff packet
- Fixed small format (target <= 500 tokens): goal, done, next step, files touched, open claim,
  last room message id read, caveats. Written by the outgoing seat or, if it died, assembled from the
  room log and git state.
- New incarnation starts from: AGENTS pointer + MEMORY-INDEX + the packet. No full history.
Done when: `seat handoff` writes it, a fresh seat resumes a real task from it in a test.

## Phase 3. CLI is the only usage source
- A single reporting call, run by the CLI, writes `{designation, model, provider, window %, weekly %,
  time}` into the seat heartbeat (M4). No scraping of other sources, no roster guesses.
- Supervisor reads only these heartbeats. A missing or stale one counts as "unknown", not "fine".
- During a switch, the same call reports before and after, so the numbers still come from the CLI.
Done when: heartbeat carries usage + model; supervisor reads it; test for stale/unknown.

## Phase 4a. THE CORE JOB: pick the model with the most usage left and type its slash command
This is the thing the system must actually do (Phil, 2026-10-22). Everything else supports it.
- Each trigger, rank the available models by **usage remaining, most first**, using only the
  CLI-reported numbers from Phase 3.
- Take the top one that is not the current model and **type its slash command into that seat's CLI**
  (`/<name of that model>`, exact syntax from Phase 0), as if Phil typed it. The seat keeps its
  designation, tab and session; only the model changes.
- Typing uses the existing terminal-input path (`tests/test_terminal_input.py` already covers a winpty
  one); no new UI-injection mechanism unless Phase 0 shows that one fails.
- Verify after typing: the CLI's next usage report must show the new model active. If not, retry once,
  then fall back to Path B below and flag it in the room.
- Order comes from usage left, not a fixed list. The preference list from decision 2 is only the
  tiebreak and the "never use this one" exclusions.
Done when: a seat near a wall is moved to the model with the most headroom with no human action, and
the next CLI report confirms it.

## Phase 4. The switch itself (shape depends on Phase 0; fallback for 4a)
- Path A, if the CLI can switch in place: a `seat switch <designation> --to <model>` tool call that
  writes the handoff packet, switches, bumps `generation`, posts one line to the room.
- Path B, if not: same command closes the tab and respawns the same designation with the new model,
  same title, packet-seeded.
- Either way the old model's session never keeps running alongside the new one.
Done when: a seat switches provider with no human action and keeps its name and open claim.

## Phase 5. Supervisor trigger (needs ballot: changes M5 behaviour)
- Deterministic loop, no model calls while idle. Existing floors: hand off at 10% left in the
  five-hour window; weekly drains to 5% then hard stop.
- Target model chosen by a preference list Phil sets (today: Gemini, then Command Code, Codex for
  review) and by headroom from the Phase 3 numbers.
- Switch at a task boundary when possible; mid-task only when the floor is about to be hit.
- Cooldown so a seat does not bounce between providers; when nothing has headroom, park the seat and
  tell Phil once.
Done when: simulated quota drain moves a seat to the next provider and posts exactly one line.

## Phase 6. Hardening
- Crash during a switch leaves exactly one live seat (or none, flagged), never two.
- Stale-lock recovery, message de-duplication, forwarding if the room needs it for one-per-designation.
- Soak run: several simulated drains in a row; gate green.

## Dependencies and order
0 -> 1 -> 2 -> 3 -> 4 -> 5 -> 6. Phases 2 and 3 can run in parallel after 1. Each phase is one claimed
task landing through the gate. Phase 0 changes nothing, so it can start immediately.

## Ballots this implies
- Roster/slot semantics and one-live-seat-per-designation (Phase 1).
- Supervisor switching behaviour and the provider preference order (Phase 5).
Phases 0, 2, 3, 4 and 6 change no rule, but should be announced in the room.

## Decisions from Phil (2026-10-22)
1. **Full automation from day one.** No approving each switch by hand.
2. **The preference order must be one of the easiest things to change.** One command sets it and
   "make current default" saves it (e.g. `megazword prefer gemini codex cmdc --default`). Stored in one
   small config file read at decision time, so a change applies on the next trigger with no code edit.
   Floors stay as today unless Phil changes them the same way.
3. **Consistency before automation.** Phil needs to rely on getting used to named bots. If that is not
   achieved first, automatic switching just makes a mess. So Phase 1 (stable names) is the gate: do not
   build Phases 4-5 until names behave consistently in real use.
4. **"Who is currently in charge" is deferred.** It is hard to answer now and Phil does not need it
   yet. Do not design a conductor-succession rule until naming is stable.
5. **The roster records the provider** per designation and per post, and **can be asked**: any seat
   can query who a designation is, which provider it runs on, and its status.
6. **Designation-to-designation requests** should be easy: one seat asks another directly instead of
   going through the conductor or Phil (see Phase 7).

## Phase 7. Seat-to-seat requests (new; needs ballot)
- `megazword ask <designation> "<question or task>"` posts a request addressed to that designation
  and returns when it answers or times out. Answers are data, not orders: only Phil's lanes carry
  authority (AGENTS.md), so an asked seat may decline.
- `megazword who <designation>` returns provider, model, generation, status, open claim.
- Requests follow the designation, not the model, so they still arrive after a switch. If the target
  is mid-switch, the request waits for the new incarnation.
- Needs the M6 grammar so an ask parses or does nothing and says why. If the room needs forwarding to
  deliver to the right live seat, the supervisor does it; Phil never sees it.
Done when: one seat asks another across a model switch and gets the answer; `who` is accurate.

## Revised order
0 (facts) -> 1 (stable names, slot + roster + `who`) -> use it for real until names feel consistent
-> 2 and 3 (handoff, CLI usage) -> 7 (ask) -> 4 and 5 (switch + auto trigger, with the easy
preference config from decision 2) -> 6 (hardening).
Phase 1 is the gate; automation waits on it.

## Still open
1. Floors: keep 10% five-hour / 5% weekly, or different?
2. What counts as "names feel consistent enough" to start Phases 4-5? (Suggest: one week with no
   duplicate designation, no wrong-provider label, no seat unreachable by name.)

## Risks
- The CLI may not expose usage or model switching; Phase 0 answers it before anything is built.
- Handoff packets are lossy; a weak packet restarts the same mistakes.
- A wrong usage reading triggers needless switches; hence "CLI only", "unknown is not fine", cooldown.
