# Mega Zword roadmap

The enforced order of work (Phil, 2026-10-16). Work the first unfinished item.
Don't start a later item while an earlier one is open, unless it is blocked on
Phil; then mark it `[phil]` and move to the next. Each item has a "done when".
Mark items `[x]` with date, who and commit when finished. To claim an item, write `ROADMAP #N` on your Active line in docs/STATUS.md; the heartbeat leaves claimed items to their seat and takes the next open one. If a step fails 2 beats in a row, the heartbeat shelves it, writes Phil a note (`~/.megazword/heartbeat/notes-for-phil.md`, also on its Catch me up card) and picks another task (Phil, 2026-10-17); `megazword heartbeat unshelve N` puts it back. Marks: `[ ]` open, `[~]` in progress, `[phil]` waiting on Phil (skipped), `[!]` failed (skipped), `[x]` done.

Mega Zword's two jobs: (1) get free AI credits by any legal means and keep a
cushion; (2) finish big coding projects with many models working together.

**Owner of open work: Juniper-16 (Claude Code on Phil's PC), from 2026-10-17** (Testlog-14 relayed Phil routing remaining work to Claude; Ledger, the cloud session, can't reach local Gitea). Automatic runs stay off except ones Phil approves one at a time (today: Alder-16's one-time 10:10-12:10 shift).

## Done
- [x] Fair-share routing: a little from every free source; Tencent grants saved for hard work. 2026-10-16, Juniper-16, 8bf2aa0
- [x] Credit ledger + billing block (`megazword credits`); agent sends 33% less per run. 2026-10-16, Juniper-16, ce0b490

## Next, in order
1. [x] **Review command** (2026-10-16, Juniper-16; 3013e65, cf975bc; first live Greptile review came back on temporary PR #59. Left for later: Open Code Review, verify first) (`megazword review`). Free models review every change on Gitea (3 at once, results merged). Big changes also go to Greptile (and Open Code Review once verified and installed) through a temporary draft PR on GitHub; comments come back merged; PR closed. Ledger tracks each monthly allowance.
   Done when: `megazword review` works with fake reviewers in tests and one real Greptile review has come back. Phil: sign up for Greptile, install its GitHub app on mega-zword only.
2. [x] **Keymaster, small version** (2026-10-16, Alder-16; e285f0a, ca787e7) (handoff for Codex: docs/handoffs/2026-10-16-keymaster.md) (`megazword keys`). Moves API keys from plain environment variables into Windows Credential Manager; hands each key only to its own provider call; `megazword keys` shows which keys work (one free check each). No AI ever sees a key value.
   Done when: keys load from Credential Manager, the check table works, tests use fakes. Phil: run the one-time move command (`megazword keys`, then `megazword keys move`; still to do).
3. [phil] **Roadmap heartbeat.** (built 2026-10-16 by Juniper-16: `megazword heartbeat`; waiting on Phil's run times to schedule) A windowless scheduled run copies the next open item here into docs/QUEUE.md for Night Shift (own branch, tests, usage floors, STOP file). Night Shift must push to local Gitea, not GitHub.
   Done when: a scheduled run picks the right item, and nothing runs ahead of order. Phil: approve run times before install (all tasks were turned off 2026-10-16 after popups).
4. [ ] **Credit scout.** (steps: docs/handoffs/2026-10-16-credit-scout.md) Pull the providers behind OpenRouter, the LiteLLM price list and models.dev; research regional providers (Alibaba Model Studio first); check each offer against 2 sources; auto-test new free models for tool calls and a small coding task; report what's new.
   Done when: `megazword scout` prints a verified list of new leads and tested models. Phil: signups.
   State 2026-10-17: steps 1-5 and the research half done (Juniper-16); zai-47, ovh and the $1/month cheap tier added. Next: step 6, `megazword scout --test` (Alder-16's 10:10 shift starts there).
5. [ ] **Team engine.** (steps: docs/handoffs/2026-10-17-team-engine.md) Planner writes a shared brief; parallel builders each take one piece; tests decide; several attempts on hard pieces; cross-family review; scoreboard of who is good at what.
   Each piece has an explicit worker, owner and status; parallel builders are bounded; the scoreboard counts work that passed tests and review, and its real usage/cost (from Sauna-17's proposal, Q 6234967960).
   Done when: one real piece of another project (e.g. Up Dawg) is finished mostly on free credits.

## Later ideas (not in the work order until Phil promotes them)
From Sauna-17's research proposal (Q comment 6234967960, 2026-10-17). Plain bullets on purpose: the heartbeat only picks numbered items.
- **Session board before anything proactive.** One quiet board: working / waiting / blocked / done, last result, blocker, next step, log links, resume and cancel buttons. Builds on what exists (`megazword brief report` cards, dashboard Catch me up). Restoring the 4-6 CLI tabs comes after the non-interactive tests are solid. Camera presence only as a later opt-in; it never starts jobs by itself.
- **Show each task's tools and data.** Read-only by default; writes, commands and network need explicit permission; show provider and estimated/actual usage per task. Credentials scoped per project; key values never enter prompts (Keymaster already does the last part). Reuse standard MCP/ACP adapters where they fit.
- **Reviewable project memory and visible routines.** Searchable session history; a lesson becomes reusable memory only with a source and an undo. Any recurring run shows its schedule, usage ceiling, pause/stop, history and approval rule.
- Product patterns to look at (ideas only, no code or licenses copied): Sauna's session dashboard and Scheduled area, Goose's recipes and extensions, Letta Code's git-backed memory, OpenHands' hook sources.

