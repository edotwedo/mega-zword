# Model switching: Phase 0 facts

Author: Forge-22, 2026-10-22. Claim: 'model-switching phase 0' (approved by Cinder-21). Read-only research;
no code written and no live injection tested. Each fact is marked **verified** (I ran it or read the file),
**reported** (web search summary of Antigravity docs, not checked against a live meter) or **untested**.

## Q1. Exact slash syntax and model names in agy

**Model names (verified, `agy models`):**

| Id | Display name |
|---|---|
| `gemini-4-argon-low/medium/high` | Gemini 4 Argon |
| `gemini-3.8-flash-low/medium/high` | Gemini 3.8 Flash |
| `claude-opus-5-5-low/medium/high` | Claude Opus 5.5 |
| `claude-sonnet-5-5-low/medium/high` | Claude Sonnet 5.5 |
| `gpt-oss-120b-medium` | GPT-OSS 120B (the "OSS-128" Phil asked about) |

The low/medium/high suffix is a reasoning effort tier of the same model, not a different model.

**Switching:**
- In a session: `/model` opens a picker; `/model <name>` switches directly, keeping the conversation
  (reported). The exact argument form (id vs display name) is **untested**; the ids above are what
  `agy models` prints and are the best first guess.
- At launch (verified, `agy --help`): `--model <name>`, `--effort low|medium|high|xhigh|max`,
  `--conversation <id>` resumes a conversation by id, `-c/--continue` resumes the latest.
- Print mode `-p/--print` runs one prompt non-interactively. `--disable-slash-commands` exists, so slash
  commands do expand in print mode by default (reported by the flag's help text; untested).

**Usage reading:**
- `/usage` (alias `/quota`) shows a TUI overlay with weekly/session limits and time to refresh (reported).
- **Gap:** `agy --help` has no usage subcommand (verified). The only reading found is the interactive
  overlay, which is not machine-readable. Phase 3's "CLI reports usage into the heartbeat" needs a way to
  get that number out: either `/usage` inside a print-mode call, or parsing the overlay, or a CLI/API route
  nobody has found yet. This is the largest open question for the plan. **Untested.**

## Q2. Does typing the slash command through the terminal-input path work?

- **Not into Forge-22's own tab, today. Verified from repo notes** (`docs/handoffs/2026-10-22-cinder-21-handoff.md`,
  `docs/STATUS.md`): Windows Terminal runs elevated, so every tab is `Administrator:` and a non-elevated
  process cannot `SendKeys` into it ("Access is denied"). Phil can type there; the supervisor cannot.
- **The repo already points at the fix:** `src/megazword/workspace_terminal.py` is "an owned terminal relay:
  queued return prompts, never SendKeys into another app", built on ConPTY/winpty. A seat launched inside
  that relay is a child of megazword, so megazword can queue input to it with no elevation problem. I read
  the file header only; I did **not** run it. Whether a seat started in the relay can take `/model <name>`
  typed into its stdin is **untested**.
- **A path that avoids typing entirely (untested):** respawn the same designation with
  `agy --conversation <id> --model <name>`. It keeps the same conversation id and tab title with a different
  model. Whether `--conversation` combined with a different `--model` keeps the history is unverified.
- Practical consequence: the supervisor cannot do "type `/model` into the tab" for existing elevated tabs.
  The plan should launch seats in the owned relay, or use the respawn route.

## Q3. Do the models share one quota or have separate pools? (decides everything)

Reported, not verified against a live meter:
- **Gemini models share one pool.** Gemini 4 Argon and Gemini 3.8 Flash draw from the same shared budget,
  weighted by relative price (cheaper Flash gets more tokens per unit). Switching Argon <-> Flash does
  **not** escape a spent Gemini pool; Flash only stretches it. The low/medium/high tiers are the same model
  and the same pool.
- **Claude and GPT-OSS sit outside the Gemini pool**, with separate fixed limits. So switching from a
  spent Gemini to a Claude or GPT-OSS model **does** buy real headroom, and so does the reverse.
  Whether Claude and GPT-OSS share one pool with each other is not stated in what I found.
- Paid tiers refresh every 5 hours but only while the weekly cap has room; the free tier resets weekly.
  AI credits can cover overage on third-party pools.

**What this does to the plan:**
1. Ranking models by "most usage left" must rank **pools**, not models. Gemini 4 Argon and Gemini 3.8
   Flash are one entry with two price weights.
2. The useful switch is **across** pools (Gemini <-> Claude <-> GPT-OSS). A Gemini-only plan would not
   avoid walls. This matches the cross-provider scope Phil kept ("stick with your original plan").
3. The room's "Google weekly is 100% used" line applies to the Gemini pool only; Claude Sonnet 5.5 (the model
   this seat shows selected) would still have its own headroom. That claim was corrected by Cinder-21.

## Verdict
The plan stands, with three changes to carry into Phase 1+:
1. Rank pools, not model ids.
2. Make switching survive the elevated-terminal limit: launch seats in the owned relay, or switch by
   respawning with `--conversation <id> --model <name>`.
3. Find a machine-readable usage source before Phase 3. Until one exists, Phase 3 is blocked.

## Next probes (not done; each needs a go, since they touch live sessions or spend quota)
- Run `agy -p "/usage"` once in a scratch folder and see if it prints the numbers.
- Start a throwaway seat via `workspace_terminal` and type `/model <id>` into it.
- Try `agy --conversation <id> --model <other-id> -p "say ok"` to see if history survives.

## ADDENDUM 2026-10-22 22:05: probes run (VERIFIED; supersedes the "reported" and "untested" notes above)

Run in a scratch folder (`%TEMP%\agy-probe`), cost a few thousand tokens total.

**Probe 1: `agy -p "/usage"` is the machine-readable usage source.** It returns tab-separated lines in
about 6 seconds, with no model reply needed:

```
Gemini Models           Weekly Limit Remaining     82%  2026-10-28T04:55:54Z
Gemini Models           Five Hour Limit Remaining  75%  2026-10-23T06:03:58Z
Claude and GPT models   Weekly Limit Remaining     32%  2026-10-28T04:54:20Z
Claude and GPT models   Five Hour Limit Remaining  47%  2026-10-23T07:55:16Z
Gemini 4 Argon          Gemini 4 Argon Weekly Limit  1%  2026-10-28T21:27:01Z
```

- This **closes the Phase 3 gap**: no TUI scraping needed. The CLI itself reports, as Phil required.
- **Real pools, from the CLI itself:** (a) **Gemini Models**, weekly and five-hour; (b) **Claude and GPT
  models**, weekly and five-hour (Claude and GPT-OSS share one pool); (c) **Gemini 4 Argon has its own
  extra weekly limit** on top of the Gemini pool. Argon at 1% means Argon is nearly walled while
  Gemini Flash still has headroom in the shared pool.
- A model is usable only if **every limit that applies to it** has room. Rank by the minimum remaining
  across its applicable limits, not by one number.
- Each limit has a reset time, so the supervisor can also report "back at HH:MM".

**Probe 2: `agy -p ... --output-format json` returns per-call usage.** Example:
`{"conversation_id":"...","status":"SUCCESS","response":"ok","num_turns":1,"usage":{"input_tokens":7006,"output_tokens":1,...}}`.
Note a one-word call to a fresh conversation cost **7,006 input tokens**: that is the CLI's fixed
overhead per fresh conversation (confirms the earlier 8-25k estimate for hello).

**Probe 3: switching model on a live conversation works, across pools.** Started a conversation on
`gemini-3.8-flash-low` ("remember PINEAPPLE"), then resumed the same conversation id with
`--conversation <id> --model claude-sonnet-5-5-low` and asked for the word: it answered `PINEAPPLE`,
`num_turns: 2`, same `conversation_id`. History survived the switch from the Gemini pool to the
Claude/GPT pool. The Claude/GPT meter then dropped (five-hour 47% to 45%, weekly 32% to 31%), so the
usage readout reflects the switch.

**Probe 4 (not run, no longer needed): typing `/model` into a live elevated TUI.** Path B above
(resume with `--conversation <id> --model <name>`) achieves the switch without typing, so the
elevated-terminal limit does not block the plan.

### Revised verdict
Phase 3 and Phase 4 are now **buildable with documented flags only**:
1. **Read usage:** `agy -p "/usage"` parsed into pool rows (weekly, five-hour, plus any per-model row).
2. **Choose:** rank pools by the minimum remaining across applicable limits; exclude any model whose
   own limit is spent (Argon) even if its pool has room.
3. **Switch:** end the seat's current agy process and start `agy --conversation <id> --model <chosen>`
   in the same tab with the same designation; the next `/usage` read must show the new pool draining.
4. **Open detail:** how the seat's running TUI is closed and relaunched in the same tab without SendKeys
   (owned relay via `workspace_terminal.py`, or launching seats through a wrapper that can restart agy).
   Needs a design decision in Phase 1/4, not more facts.
5. **Interactive TUI vs print mode:** these probes used print mode. A seat in the interactive TUI
   resuming a conversation by id with `--model` should behave the same, but that exact path is not yet
   run.
