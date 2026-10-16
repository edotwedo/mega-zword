# Mega Zword roadmap

The enforced order of work (Phil, 2026-10-16). Work the first unfinished item.
Don't start a later item while an earlier one is open, unless it is blocked on
Phil; then mark it `[phil]` and move to the next. Each item has a "done when".
Mark items `[x]` with date, who and commit when finished. To claim an item, write `ROADMAP #N` on your Active line in docs/STATUS.md; the heartbeat waits on claimed items and never skips ahead. Marks: `[ ]` open, `[~]` in progress, `[phil]` waiting on Phil (skipped), `[!]` failed (heartbeat stops), `[x]` done.

Mega Zword's two jobs: (1) get free AI credits by any legal means and keep a
cushion; (2) finish big coding projects with many models working together.

## Done
- [x] Fair-share routing: a little from every free source; Tencent grants saved for hard work. 2026-10-16, Juniper-16, 8bf2aa0
- [x] Credit ledger + billing block (`megazword credits`); agent sends 33% less per run. 2026-10-16, Juniper-16, ce0b490

## Next, in order
1. [phil] **Review command** (free-model half done 2026-10-16, Juniper-16: `megazword review [--base REF] [-n 3]`; Greptile half coded with `--greptile`, needs one live run once Claude may push review branches to GitHub) (`megazword review`). Free models review every change on Gitea (3 at once, results merged). Big changes also go to Greptile (and Open Code Review once verified and installed) through a temporary draft PR on GitHub; comments come back merged; PR closed. Ledger tracks each monthly allowance.
   Done when: `megazword review` works with fake reviewers in tests and one real Greptile review has come back. Phil: sign up for Greptile, install its GitHub app on mega-zword only.
2. [x] **Keymaster, small version** (2026-10-16, Alder-16; e285f0a, ca787e7) (handoff for Codex: docs/handoffs/2026-10-16-keymaster.md) (`megazword keys`). Moves API keys from plain environment variables into Windows Credential Manager; hands each key only to its own provider call; `megazword keys` shows which keys work (one free check each). No AI ever sees a key value.
   Done when: keys load from Credential Manager, the check table works, tests use fakes. Phil: run the one-time move command.
3. [~] **Roadmap heartbeat.** (built 2026-10-16 by Juniper-16: `megazword heartbeat`; waiting on Phil's run times to schedule) A windowless scheduled run copies the next open item here into docs/QUEUE.md for Night Shift (own branch, tests, usage floors, STOP file). Night Shift must push to local Gitea, not GitHub.
   Done when: a scheduled run picks the right item, and nothing runs ahead of order. Phil: approve run times before install (all tasks were turned off 2026-10-16 after popups).
4. [ ] **Credit scout.** Pull the providers behind OpenRouter, the LiteLLM price list and models.dev; research regional providers (Alibaba Model Studio first); check each offer against 2 sources; auto-test new free models for tool calls and a small coding task; report what's new.
   Done when: `megazword scout` prints a verified list of new leads and tested models. Phil: signups.
5. [ ] **Team engine.** Planner writes a shared brief; parallel builders each take one piece; tests decide; several attempts on hard pieces; cross-family review; scoreboard of who is good at what.
   Done when: one real piece of another project (e.g. Up Dawg) is finished mostly on free credits.
