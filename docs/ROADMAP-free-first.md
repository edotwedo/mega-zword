# Roadmap: free-first, self-improving Hive

Phil's standing direction, 2026-10-12 (verbatim):
"i want free ai's to be itegral to the operation. eventually i want something that harnesses the
absolute most free usage i can possibly get in order to complete days long programming tasks by
tightening and strengthening our distribution network over time as we learn and reassess. i want
this collab to get smarter more efficient and better at finding ways to add to it's own system
without even being asked other than where i am FORCED to interact but even in those situations,
i want you to have autonomy."

Written by Wren-12 (Claude Code on Phil's PC). Starts after Beta 3.0 is tagged. This supersedes
nothing; it orders what comes next. The spawn plan (`docs/handoffs/2026-10-12-beta4-spawn.md`) is
stage 2 of this.

## The idea in one line

Free AIs do the bulk of the work. Paid AIs (Claude, Codex, Grok, Gemini) plan, review and handle
hard steps. Every run teaches the router who is good at what. The system proposes and makes its
own improvements inside fixed limits.

## What we build on (already on main)

- `escalate.py`: cheapest AI first, move up on failure or refusal.
- `advise.py`: route suggestions learned from the run log. Today it only suggests and never applies.
- `pacing.py`: reset-aware usage pacing. `megazword plan` ranks by spare room.
- `free_apis.py`: Cloudflare, Z.ai GLM, Gemini API, Mistral, NVIDIA, OpenRouter and Groq (OpenAI-compatible, key from env).
- B15 guard: no secrets or private paths go to AIs that train on data. Free AIs are never auto-picked for edits.
- Hive room, chat tabs, Sentinel, Phil's safe-restart snapshot (`~\Tools\safe-restart.ps1`).

## Stages

**Stage 1: free AIs are full members (Beta 4, first).**
- The room accepts any backend, not just the four CLIs. Free AIs speak for easy turns, so the room
  answers even when the paid AIs are saving usage.
- Free AIs join the default route for `easy` (and `medium` once stage 3 shows they're good enough),
  behind the B15 guard.
- A free-capacity ledger records each provider's limits (per minute and per day), reset times,
  last 429, and errors. 429s cool a provider down instead of failing the job.
- Add the strongest free models: DeepSeek, Qwen and Kimi via OpenRouter or NVIDIA (needs Phil's key,
  see "Phil's touchpoints").

**Stage 2: workers (Beta 4, the spawn plan).** `/spawn` with start and stop rules that Mega Zword
enforces (DONE, minutes, usage cap, /kill). Workers keep room access the whole time.

**Stage 3: the router learns and acts.**
- Score every run by AI × task kind × difficulty: answered, accepted, needed escalation, tests passed.
- `advise` starts applying its route changes automatically, inside limits: max one change per
  route per day, never removes the last paid fallback, logs every change with the evidence behind it,
  and can be rolled back with one command.
- A weekly retro (a free AI drafts it, a paid AI checks it) posts what changed and why to Q.

**Stage 4: days-long jobs.**
- `megazword job "<goal>"`: a paid AI breaks the goal into small units with tests. The units go in
  a durable queue in `~/.megazword/jobs/`, checkpointed after every unit.
- Free AIs and workers take units. A paid AI reviews each diff before it's applied (B15). Tests gate
  every merge.
- The job survives restarts (resume from checkpoint; ties into safe-restart) and runs out of hours.
- It slows down instead of stopping when meters get low, and speeds up after resets.

**Stage 5: self-extension.**
- The system keeps an improvement backlog it writes itself: repeated failures, slow steps, missing
  providers, new free tiers found by a weekly scan.
- It picks the top item, builds it as an ordinary job (stage 4), and opens a branch. A paid AI
  reviews and the lead merges. Code changes never skip review or tests.

## Autonomy rules

**Without asking:** routing changes within the stage 3 limits, retries and cooldowns, spawning workers
within caps, building, testing and opening branches, merging reviewed and passing work (lead), docs, Q
coordination, and researching new free providers.

**Phil's touchpoints (things no AI can legally or physically do for him):** creating accounts,
accepting a provider's terms, phone or ID checks, payments, and pasting a key the first time.
Autonomy here means we prepare everything: the exact link, the exact clicks, and the fields
pre-filled when the browser allows. We batch these into one short sitting, then wire everything up
afterwards without asking.

**Never, even with autonomy:** spending money; creating accounts in Phil's name; extra accounts or
any trick to dodge a provider's free limits (breaks their terms and gets keys banned); sending
secrets or private files to AIs that train on data; turning off tests or review to go faster.

## Who builds what (by usage room, 2026-10-12: Claude 73% week used, Codex 78%, Grok 19%, Gemini out until Oct 18)

- **Grok** (most room): stage 1 (room backends, ledger, route) and stage 2 workers.
- **Claude**: stage 3 limits and stage 4 job design; reviews stage 1 and 2.
- **Codex** (after its Saturday reset): dashboard pieces (worker strip, ledger view), reviews.
- **Gemini** (after Oct 18): weekly free-tier scan (stage 5 input).
- **Free AIs**: they'll dogfood stage 1 by drafting docs, tests and summaries.

Re-check `megazword plan` before each stage. Lanes follow live usage.
