# Extract: what Mega Zword and RobinTHood take from Freebuff

Tern-25 (Claude cloud), 2026-10-25, for Phil. Hive item #745.

Source read: github.com/CodebuffAI/codebuff (Freebuff and Codebuff are the same repo), shallow clone of 2026-10-25.
License: Apache-2.0. We may copy code, but every copied file keeps their copyright line, and we add their
`NOTICE` text ("Codebuff, Copyright 2025 Codebuff") to ours. Reading ideas and rewriting them needs nothing.

Rule: we read their source only. Nobody installs Freebuff or runs it on our repos. It collects prompts and code.

## Short version

| # | What they have | Where it goes for us | Size of win |
|---|---|---|---|
| 1 | Mechanical history compaction, no model call | `agent.py` history handling | Biggest. Their note: strips ~87% of a tool-heavy history |
| 2 | "Lean context" prompt section | `agent.py` system prompt | Cheap, tested |
| 3 | Per-model compaction tied to the provider's cache life | `agent.py` + `routing.py` | Medium |
| 4 | tree-sitter code map | `repo_map.py` (only for C# and other languages) | Small, but RobinTHood is C# |
| 5 | BuffBench: score agents by rebuilding real commits | `scores.py` / `free_test.py` | Medium, longer job |
| 6 | Ad slots, hours meter, earn-hours | RobinTHood desktop and Android | Business model |

## 1. Mechanical compaction (biggest token win)

Their file: `packages/agent-runtime/src/compact-history.ts` (1,452 lines; a copy also lives in `agents/context-pruner.ts`).

What it does, with no model call:
- Each old message is cut to a cap: user 13,000 chars, assistant 1,300, each tool entry 5,000.
  Long text keeps 80% head and 20% tail.
- Old tool calls become one-line summaries ("read src/x.ts", "ran: npm test").
- Read files become an outline with line numbers. The newest reads stay in full.
- Remaining todos are carried over, so the model knows what is left.
- Budgets: 20,000 tokens for assistant and tool history, 50,000 for user text. Counted as chars / 3.
- It triggers at 80% of the model's context.

What we have now (`agent.py`): `HISTORY_CHARS = 90_000`, condense every 10 steps
(`COMPACT_EVERY`), `_trim_stale`, and a `_progress_note`. Ours replaces history with a short note.
Theirs keeps a structured log plus file outlines, so the model does not re-read files.

Take: port the per-message caps, the one-line tool-call summaries, and the read-file outlines into
`_trim_stale` / `_progress_note`. Keep our step caps and telemetry. Measure with the existing
`step` events (`sent_chars`, `tool_chars`). Target from Lumen-20's handoff: same pass rate at 60%
or less of the tokens.

## 2. The lean-context prompt (cheap, already tested)

Their file: `agents/lean-context.ts`. They tested it on their benchmark with a small model held
under 100k tokens. Compaction alone cost about 0.5 points; adding this text cut the loss to about
0.2 and halved how often a run had to compact.

Their key findings, worth copying as ideas:
- Telling a model to save context makes it **do less of the task**. The prompt must say the budget
  limits how you read, never how much you do.
- A written todo list is what lets the model resume after compaction.
- Search wide, read narrow: read a whole file only if it is about 100 lines; otherwise read a
  100-250 line window. Do not re-read unchanged lines.
- Filter long command output (`tail -n 50`) but keep the exit status.
- Before finishing, search for leftover references to anything renamed or removed.

Take: add a short section like this to our system prompt in `agent.py`. Keep the prompt
byte-identical every step so caching still works.

## 3. Compact on cache expiry, per model

Their file: `common/src/constants/compaction-policy.ts`.

Idea: when a provider's prompt cache has expired, the next call pays full price for the whole
history anyway. So that is the moment to compact. Their default is 1 hour and 140k tokens. For
DeepSeek Flash they use 15 minutes and 40k, because that provider keeps cache about 15 minutes and
a cold token costs about 40 times a cached one.

Take: add a per-model "cache life" field next to the routing data, and compact after an idle gap
longer than that. Matters for long jobs that pause (rate limits, Phil away).

## 4. Code map (only where regex is not enough)

Their package: `packages/code-map` uses tree-sitter queries for many languages.
Ours: `src/megazword/repo_map.py`, regex, Python and JS/TS only, about 1.5k tokens.

Ours is the right size for Python and TypeScript. Keep it. The gap is C#: RobinTHood and Spanda are
C#, and our map sees nothing there. Take: either add a C# regex (class / method signatures), or copy
their C# tree-sitter query file if regex proves too rough.

## 5. Score models on real work before routing to them

Their folder: `evals/buffbench`. A task is a real past commit. The agent rebuilds it from the
commit message, then a judge scores completion and code quality, and the repo's own test command
gives a pass/fail. They also compare two setups side by side (`compare-arms.ts`).

Take: use our own merged commits as tasks for `scores.py`. This tells us which free models can be
trusted with which kind of job, which is item 6 (route by task shape) in Lumen-20's handoff.

Also: `agents/base3-free-*.ts` is one small file per free model on top of one shared base. That is a
clean pattern for `docs/FREE-MODEL-ROSTER.md` and `routing.py`.

## 6. RobinTHood: their business model, already running

Freebuff is free AI paid for by ads, which is RobinTHood's plan. What they built (`cli/src`):

- **Ad network:** they use Gravity (`api.trygravity.ai`), an ad network for AI apps. RobinTHood's
  ad engine uses house ads and sponsor rotation today. Gravity is worth checking as a paid-fill
  source. Phil's call; no sign-up without him.
- **Ad slots:** one slot, one ad. A banner on the start screen and a single status-line row.
  Every ad says "Ad". The user can hide it for the session with ×. If no ad is served, the slot
  draws nothing (no empty box).
- **Billing events:** impression counted when the ad is shown, click counted before the link opens.
- **Sponsored offers:** "Set it up" opens a consent screen; it never accepts on one click.
- **Hours meter:** usage is sold in one-hour sessions. Cheap models are unmetered. An hour that was
  bought but never used is refunded after 5 minutes. The app re-checks the price before spending.
- **Earn hours:** referrals pay when the friend sticks around. A faster "engagement" route pays
  within a minute. Bounties too.
- **Limits:** full access in supported regions, a smaller daily allowance for other regions and VPNs.

Take for RobinTHood: copy the ad rules (label, ×, no empty slot, honest click counting) and consider
an hours meter instead of fake "SAVED $" numbers. This fits the decided PROD-1 change (show measured
answers and time, not invented savings).

## Next steps (for the seat that claims this)

1. Items 1 and 2 first, in `agent.py`, measured against a baseline job. One seat owns `agent.py`.
2. Item 4: a C# addition to `repo_map.py`.
3. Item 6: hand the ad-rules list to Anvil-22 for RobinTHood.
4. Items 3 and 5 after that.

Copying any of their code: keep their file header, add their NOTICE line to our NOTICE, and say so in
the commit.
