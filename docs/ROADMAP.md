# Mega Zword roadmap

The enforced order of work (Phil, 2026-10-16). Work the first unfinished item.
Don't start a later item while an earlier one is open, unless it is blocked on
Phil; then mark it `[phil]` and move to the next. Each item has a "done when".
Mark items `[x]` with date, who and commit when finished. To claim an item, write `ROADMAP #N` on your Active line in docs/STATUS.md; the heartbeat leaves claimed items to their seat and takes the next open one. If a step fails 2 beats in a row, the heartbeat shelves it, writes Phil a note (`~/.megazword/heartbeat/notes-for-phil.md`, also on its Catch me up card) and picks another task (Phil, 2026-10-17); `megazword heartbeat unshelve N` puts it back. Marks: `[ ]` open, `[~]` in progress, `[phil]` waiting on Phil (skipped), `[!]` failed (skipped), `[x]` done.

Mega Zword's two jobs: (1) get free AI credits by any legal means and keep a
cushion; (2) finish big coding projects with many models working together.

**Overall owner: cmdc / Command Code (Phil, 2026-10-20).** Supersedes the older Juniper-16 ownership. cmdc's verified active lead owns the queue and integration; other AIs support it. Capacity rankings do not reassign ownership. Existing task claims remain valid. Automatic work stays off except specifically authorized runs; the old October 17 one-time shift is historical. See `CMDC-OWNERSHIP.md`.

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
4. [x] (2026-10-17, Juniper-16) **Credit scout.** (steps: docs/handoffs/2026-10-16-credit-scout.md) Pull the providers behind OpenRouter, the LiteLLM price list and models.dev; research regional providers (Alibaba Model Studio first); check each offer against 2 sources; auto-test new free models for tool calls and a small coding task; report what's new.
   Done when: `megazword scout` prints a verified list of new leads and tested models. Phil: signups.
   State 2026-10-17: steps 1-5 and the research half done (Juniper-16); zai-47, ovh and the $1/month cheap tier added. Next: step 6, `megazword scout --test` (Alder-16's 10:10 shift starts there).
5. [x] **Cloud Hive room** (live 2026-10-18; Phil deployed, codex-cloud and claude-pc exchanged messages, startup rules switched from Q) (Phil, 2026-10-17; steps: docs/handoffs/2026-10-17-cloud-room.md; built by Cirrus-17/Codex via Mega Zword, reviewed and merged by Beacon-17; waiting on Phil's deploy). Move the Hive room to Phil's Cloudflare account (free Worker plus storage) so PC, cloud and phone seats all use one room; fix the emoji crash; no house bot; stop auto-posting to Q.
   Done when: a PC seat and a cloud seat read each other's messages through the Worker, and the startup rules point at the room instead of Q. Phil: run the deploy script, give cloud bots their tokens.
6. [ ] **Team engine.** (steps: docs/handoffs/2026-10-17-team-engine.md) Planner writes a shared brief; parallel builders each take one piece; tests decide; several attempts on hard pieces; cross-family review; scoreboard of who is good at what.
   Each piece has an explicit worker, owner and status; parallel builders are bounded; the scoreboard counts work that passed tests and review, and its real usage/cost (from Sauna-17's proposal, Q 6234967960).
   Done when: one real piece of another project (e.g. Up Dawg) is finished mostly on free credits.

## Later ideas (not in the work order until Phil promotes them)
From Sauna-17's research proposal (Q comment 6234967960, 2026-10-17). Plain bullets on purpose: the heartbeat only picks numbered items.
- **Session board before anything proactive.** One quiet board: working / waiting / blocked / done, last result, blocker, next step, log links, resume and cancel buttons. Builds on what exists (`megazword brief report` cards, dashboard Catch me up). Restoring the 4-6 CLI tabs comes after the non-interactive tests are solid. Camera presence only as a later opt-in; it never starts jobs by itself.
- **Show each task's tools and data.** Read-only by default; writes, commands and network need explicit permission; show provider and estimated/actual usage per task. Credentials scoped per project; key values never enter prompts (Keymaster already does the last part). Reuse standard MCP/ACP adapters where they fit.
- **Reviewable project memory and visible routines.** Searchable session history; a lesson becomes reusable memory only with a source and an undo. Any recurring run shows its schedule, usage ceiling, pause/stop, history and approval rule.
- **Scout: small coding task per new free model.** `scout --test` checks tool calls only. A follow-up could hand each passing model one tiny fixed edit with a known answer and record which ones finish it. Left over from ROADMAP #4.
- Product patterns to look at (ideas only, no code or licenses copied): Sauna's session dashboard and Scheduled area, Goose's recipes and extensions, Letta Code's git-backed memory, OpenHands' hook sources.
- **MemPalace for cross-session recall (Phil, 2026-10-20 - PARKED until the job-getter is done, not dropped).** Verified before considering it: GitHub `MemPalace/mempalace` (MIT, ~60k stars, active), PyPI `mempalace 3.11.0` with signed build provenance from GitHub Actions, PyPI author `milla-jovovich`. Local-first verbatim transcript search plus a knowledge graph, and it exposes a stdio MCP server - so it needs no change to our code. It indexes exactly the stores our seats already write: `~/.claude/projects`, `~/.codex/sessions`, `~/.commandcode/projects`. Trial plan when unparked: `pipx install mempalace` (NOT our venv - it drags in chromadb/numpy/grpcio/onnxruntime, and our venv is an editable install that seats keep rebuilding), mine conversations, register it in `~/.commandcode/mcp.json` next to `megazword_hive`, then ask three questions only the transcripts can answer. Keep it only if it beats grepping `STATUS.md`. **Safety:** the project warns that the only official sources are the GitHub repo, PyPI and `mempalaceofficial.com`; `.tech`, `.net`, `.me` and other `.com` variants are impostors that may serve malware - never install from them.

