# Features queued for Mega Zword

## argue mode - Phil, 2026-10-21

**Why it exists.** The room converges too fast. A proposal gets three "yes" votes and the weak
assumption underneath it survives because nobody had a reason to attack it. Argue mode gives every
seat a *reason*: it assigns stances instead of asking for opinions, so disagreement is the job rather
than a social risk.

**When it starts.** Phil's condition: when the whole team is ready to start something new. Until then
it is queued here, not built.

### Commands

    megazword argue new "<proposition>" [--rounds 2]
    megazword argue cast <id> <stance> "<argument>"      # stance: for | against | alternative
    megazword argue close <id>

### How a round works

1. `argue new` records the proposition and **assigns stances**, deliberately not by preference: a
   seat that proposed the idea is given *against*, and a skeptic gets *for*. Nobody argues their own
   first instinct, which is the whole mechanism.
2. Each seat posts exactly one argument, tagged by the parser the way `vote` tags a ballot:
   `<designation>: argue P1 for | <argument>`
3. Round two, if asked for: each seat must **steelman one opposing argument and then name the
   assumption it rests on** - `argue P1 <seat> rebuts <other-seat>`.
4. `argue close` reads the room fresh and prints a digest: arguments by stance, the assumptions
   named, objections nobody answered, and a list of **ideas surfaced that were not in the
   proposition**.

### Rules of the mode (enforced in the parser, not by politeness)

- An argument must name a **concrete failure case**. "I am not convinced" is rejected outright.
- **Agreement is not an argument.** "I agree because it is good" is rejected: a `for` stance must
  still state the strongest objection it had to overcome.
- Every round must yield at least one **thing the seat nearly missed**. That is the deliverable; the
  digest collects them.
- Length cap per argument (600 characters) to keep the token bill honest, and one argument per seat
  per round so nobody floods.

### Delivery

Same problem as broadcasts: a room post does not wake a seat. So `argue new` must be delivered into
each window (the way ballots are), with an ntfy page as the fallback when Phil is at the keyboard.
This is the second consumer of the instruction-ingress work (M6), which is why it waits for it.
