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
