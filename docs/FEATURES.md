# Features queued for Mega Zword

## Convention - a room where live coding agents argue about facts

Phil, 2026-10-21: *"a real robust chat interface where ACTIVE CODING AGENTS convene to argue about
facts like people do, purposefully picking alternative viewpoints with the goal of either breaking
bad logic or testing it as good."* And: *"if needed, we can have it argue however it argues behind the
scenes and just show an english interpretation onscreen."*

That last sentence removes the only real objection to the strict-schema design: **JSON on the wire,
English on the screen.** The agents pay the structure cost; Phil never reads it.

### Why structure at all, when chat is free

The Google Drive proposal ("Multi-Agent Inter-Model Dialogue Architecture, Anti-Drift Orchestration")
names the failure modes we hit all night, in its own words: sycophancy spirals (models agreeing to be
agreeable), goal drift from unbounded prose turns, context inflation from pleasantries and reciprocal
summaries, and role collapse when an assistant is soft-prompted into a persona. We saw every one of
those. Free chat between agents drifts within a handful of turns.

### The pieces, mapped onto what already exists

| Piece (doc) | What it becomes here |
| --- | --- |
| Deterministic Turn Referee | `megazword convene` - a Python state machine that owns turn order, never lets agents talk directly |
| Turn isolation (no shared raw context) | each seat is handed only the current proposition plus the *structured* turns it must answer; never the raw history |
| Strict payload schema | `AgentTurn` below, validated on ingest, malformed turns retried once then dropped |
| Role specialization | Proposer / Challenger / Judge, plus **Alt** for the rival thesis - assigned, not chosen |
| Spool directory | `~/.megazword/convene/<id>/round-NN-<seat>.json` plus `state.json`, auditable, never fed back |
| Convergence by test, not consensus | a round ends when the Challenger has no unaddressed defect *and* the Judge's checks pass; otherwise another round |
| Termination invariants | `N_max` rounds (default 5), per-turn character ceiling, `escalate_human` state on exhaustion |
| *(new)* Translation | every turn carries a one-line `english` the seat writes itself - no second model, no cost |

### The turn payload

```json
{
  "agent": "Briar-20",
  "round": 1,
  "stance": "against",
  "claim": "the single-integrator merge queue stalls the whole team when it dies",
  "evidence": "the queue has one consumer; nothing drains it while that process is down",
  "attacks": "Cinder-21",
  "test": "kill the integrator mid-round and see whether any other seat can merge",
  "nearly_missed": "the deputy question - who takes over, and how they know to",
  "english": "Briar says the merge queue has a single point of failure and the fix is a named deputy.",
  "verdict": "unresolved"
}
```

`english` is mandatory and is what the room renders. Everything else is for the referee and for the
spool.

### Assigned, not chosen

The mechanism that makes this different from a normal chat: **stances come from the referee, not the
seat.** A seat that proposed the idea is given *against*. A skeptical seat is given *for*. The
Challenger is forbidden from emitting praise - the doc's line, and it is the whole cure for
sycophancy. Nobody argues their own instinct, so agreement is not the easy path.

### What Phil sees

A **Convene** tab in the dashboard (the Hive tab already exists there): one card per round, each
turn shown as its `english` line with the stance and the seat, a column for defects still unanswered,
and a final card when the Judge passes or the round cap is hit. Plus a replay from the spool, so any
argument can be re-read later without spending a token.

### First slice, in order

1. `megazword convene start "<proposition>" --rounds 5` - allocate the id, spool the state, assign
   stances, post the first round's assignments into each seat's window (the delivery problem is
   already solved for ballots: typed line, ntfy fallback).
2. `megazword convene cast <id> <stance> "<claim>" --evidence ... --test ... --english ...` - the
   seat's turn, validated and spooled.
3. `megazword convene round <id>` - referee checks for unaddressed defects, issues the next round or
   closes it.
4. Dashboard tab rendering the spool.

Steps 1-3 are one module and one CLI surface, testable with injected turns. Step 4 is UI over a
directory that already exists.

## argue mode (earlier, smaller note - superseded by the above)

The original request was narrower: assign stances, forbid agreement, require each seat to name one
thing it nearly missed. All of that survives above as the payload's `nearly_missed` field and the
Challenger's no-praise rule. Build the convention room, not both.
