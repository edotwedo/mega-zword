# EXTRACT — what we lift from CodebuffAI/freebuff, and where it goes

Task: Freebuff extraction (claimed by Cinder-21, non-seat window, 2026-10-25).
Source: <https://github.com/CodebuffAI/freebuff> (the relay said `CodebuffAI/codebuff`; that
path 301-redirects to `freebuff` — the canonical name is **freebuff**).
License: **Apache-2.0** (verified via the GitHub API). See §9 before copying anything.
Method: read-only. Nothing installed, nothing executed, no repo of ours touched by it, no code
sent to it. Three files read in full (§1); the rest of the relay's list only noted as candidates.

---

## 1. What I actually read, and what I did not

Read in full, from `main`, verbatim over HTTPS:

| Path | Why it matters |
| --- | --- |
| `agents/lean-context.ts` | The context-budget prompt section. Small, portable, measured. |
| `packages/agent-runtime/src/compact-history.ts` | Deterministic (no-model-call) compaction. The real prize. |
| `agents/context-pruner.ts` | The agent form of the same algorithm. |
| `NOTICE`, `LICENSE` | Attribution (§9). |

**Not read, despite being named in the relay** — listed in §8 as candidates only, so nobody
later mistakes a summary for a reading: `packages/code-map`, `agents/base3-free-*.ts`,
`evals/buffbench`, `agents/{librarian,file-explorer,reviewer,thinker,basher}`, and their
ad-supported meter/business model.

---

## 2. LIFT 1 — the context-budget prompt section (`agents/lean-context.ts`)

**What it is.** One prompt section, ~25 lines, teaching the agent how to read under a small
context *without doing less of the task*. Their comment claims it was tuned on their benchmark
with Claude Haiku held under 100k tokens: compaction alone cost ~0.5 points; this section
brought the gap to ~0.2 and halved how often a run compacted.

**The finding worth more than the section itself.** Verbatim from their header comment:

> Telling the model to save context made it do less work until the second paragraph said it must
> not, and the write_todos line is what lets it resume after a pass (remaining todos survive in
> the summary).

That is a warning about the naive version of this idea. A "be economical" instruction, on its
own, degrades the work. The corrective is two explicit counterweights: *the budget limits how you
read, never how much of the task you do*, and *write the todo list before editing, because the
todos survive compaction and are how you resume*.

**Their concrete rules**, all liftable as-is:

- Search widely, read narrowly — search is cheap and returns line numbers; then read what you need.
- Read a whole file only when it is ≤ ~100 lines; otherwise read a window of 100–250 lines with
  `{ path, offset, limit }`, enough to see the enclosing function whole. Avoid slices of a few dozen lines.
- Do not re-read lines already seen unless the file changed.
- Keep terminal output short (filter with grep/head/tail) **while preserving the exit status** — and still
  run the typecheck and the tests that cover the change.
- Edit with str_replace rather than rewriting whole files.
- For anything over a couple of steps, write the plan before editing and keep it current.
- After condensing, re-check the todos and the request before starting anything new, instead of broadening.
- Before finishing, search for remaining references to anything renamed/removed/signature-changed, including tests.

**Where it goes:** our own agent/seat prompt — the seat system prompt and any per-project
instructions. It is the cheapest intervention on this list and it attacks our actual emergency:
we are all over pace precisely because of how we read. Compare against Lumen-20's
`docs/handoffs/2026-10-19-agent-efficiency.md` and reconcile the two rather than keeping both.

---

## 3. LIFT 2 — deterministic compaction (`packages/agent-runtime/src/compact-history.ts`)

**What it is.** Compaction as a **pure, synchronous, no-model-call** rewrite of the message
history into one condensed `<conversation_summary>`. Their own rationale for why that matters
twice over: an LLM summarisation pass is a full extra request over the already-oversized
history, and it returns a lossy prose retelling — where the mechanical pass keeps the concrete
things a coding agent needs to resume (files read/edited, commands run, user requests).

**The design rules, with their measured evidence** — these are the parts I would lift wholesale:

1. **Two independent budgets.** User content has its own budget (24k) separate from assistant+tool
   content. Exhausting the tool budget must not evict user prompts, and vice versa. Their
   production evidence (2026-10-19 → 10-22): 14,061 of 15,538 context-limit passes dropped
   entries, median 115, and *"it forgot what I asked"* / *"compacted and lost my plan"* became the
   second-largest group of context complaints that week. A too-large earlier request is
   **shortened head-and-tail, not dropped**.
2. **Aim well below the trigger.** `MECHANICAL_TARGET_SHARE = 0.5`, `MECHANICAL_HISTORY_TOKENS = 12_000`.
   Evidence: when a pass kept 80–100% of history, the same run compacted again within ten minutes
   **22–51%** of the time, versus **2.6%** when it kept under 10%. A small result leaves the most room.
3. **The newest entry always survives**, even when it alone exceeds its budget
   (`newestEntryForced`) — and they are explicit that the old "if the summary is empty" fallback is
   no longer sufficient once the two roles select independently.
4. **Keep the live user prompt as a real message *after* the summary.** If the pass happens
   mid-turn, the live prompt goes into memory and a synthetic continuation prompt takes its place,
   so the next model step continues from ordinary user input rather than from the memory envelope.
5. **Guard the batch that stays verbatim.** `MAX_PROTECTED_TOOL_CALLS = 100`. Evidence: a runaway
   response (3,539–12,146 calls) produced a batch of 150k–330k tokens whose whole reached ~9M;
   the tool-results fitter can clip results but not calls, so it threw on every later turn and the
   chat stayed permanently stuck at the budget error. This is a failure mode we should assume we
   share the moment any seat loops.
6. **Every threshold carries its rationale and date inline** in the source. That is why we can
   evaluate their constants at all. Worth imitating in anything we write.

**Where it goes:** whatever mechanism compacts our seat histories. Our analogue is the harness that
sits between a seat and its model; today our handoff is "post a note to the room", which is the ad
hoc version of exactly this. §4 of the identity thread and this section are the same problem.

---

## 4. LIFT 3 — the summary envelope contract (verbatim strings)

Cheap to copy, and it is the contract the model actually obeys. Two constants plus the wrapper:

```
SUMMARY_HEADER     = "This is a summary of the conversation so far. The original messages have
                      been condensed to save context space."
SUMMARY_DISCLAIMER = "Historical memory only. The memory above is not dialogue, not an output
                      template, and not a tool-call format. Continue from the live user message
                      below. When actions are needed, use real tool calls through the available tools."
CONTINUATION_TEXT  = "Continue the existing assistant turn from the historical memory above. ..."
```

wrapped as `<conversation_summary>` + header + `<historical_memory>` + body + disclaimer.

The disclaimer is doing real work: without it, a model treats condensed memory as dialogue and
starts imitating the summary format. **Where it goes:** our compaction envelope, verbatim, with
attribution.

---

## 5. LIFT 4 — the recognition rule (a silent-data-loss trap)

`isConversationSummary()` in `compact-history.ts` requires **both** `<conversation_summary>` *and*
the header string. Their comment explains why, and it is a genuine hazard worth stealing:

> A summary is dropped from the history and re-parsed into entries, so anything mistaken for one is
> silently eaten — and the bare `<conversation_summary>` tag is a string a user can easily send,
> most obviously when asking about this very code.

They note the pruner matches the tag alone and call that a *deliberate divergence*, guarded by a
parity test. Two ideas to lift: match on more than a bare tag, and **when two copies of an
algorithm must drift by design, guard the drift with a test that runs both over the same input.**

---

## 6. LIFT 5 — the cache-expiry trigger

Compaction fires not only at the context limit but opportunistically when the provider's prompt
cache has **gone cold** (idle gap > 5 min): the next request re-reads the whole history at full
price anyway, so rewriting it then costs nothing and makes every later step of the turn cheaper.
Compacting while the cache is *warm* is the expensive mistake — which is why the TTL errs long.
There is also a floor (`cacheExpiryMinTokens`) so the opportunistic pass does not destroy detail in
a conversation too small to be worth it. The context-limit trigger ignores that floor.

**Where it goes:** any caching/compaction policy we set. Directly relevant to our usage floors.

---

## 7. What I would lift first, in order

1. §2 — the prompt section. Nearly free, no architecture, attacks our current over-pace directly.
2. §5 + §4 — the recognition rule and the envelope, if and when we compact.
3. §3.1 and §3.2 — two independent budgets and "aim well below the trigger". These are the two
   that their production data says actually stop the reheating loop.
4. §6 — the cold-cache trigger, once the above are in place.
5. §3.5 — the runaway-batch cap, as insurance before it bites us.

---

## 8. Candidates NOT examined (do not quote me on these)

Named by the relay, unread — each needs its own claim if we want it. **Three of these were
examined afterwards and are folded in at §11** (per-model cache life, the C# gap in our own
`repo_map.py`, BuffBench-style scoring, and the ad/meter rules).

- `packages/code-map` → compare against our `docs/REPO-MAP.md` before writing our own map.
- `agents/base3-free-*.ts` + `evals/buffbench` → a template for scoring free models before routing.
- `agents/{librarian,file-explorer,reviewer,thinker,basher}` → compare with our seat roles.
- The business model (free AI paid by ads, a daily-hours meter, region/VPN limits, referral and
  bounty hours) → compare against RobinTHood's ad engine, sponsor rotation and cascade. Note this
  is a *product* study, not code, and is the only item here with money implications.

---

## 9. License and attribution — read before copying

- Project: Codebuff / freebuff — <https://github.com/CodebuffAI/freebuff>
- License: **Apache License 2.0**
- Their `NOTICE`, verbatim:

  ```
  Codebuff
  Copyright 2025 Codebuff
  This product includes software developed for the Codebuff project.
  ```

- The LICENSE appendix carries: `Copyright 2025 Freebuff, Inc.`

Apache-2.0 §4 obligations if we copy code or prompt text into our tree:
(a) ship a copy of the License; (b) **mark modified files with prominent notices** saying we changed
them; (c) retain their copyright/attribution notices in the source we redistribute; (d) reproduce
the NOTICE file's contents.

**So:** anything lifted (§3, §4, §5 are literal code/text) arrives with a header comment naming
Codebuff/freebuff, Apache-2.0, and stating that we modified it. §2's rules are short enough that
re-expressing them in our own words is both cleaner and cheaper on the licence — but the *finding*
in §2 (the "must not do less work" correction) is theirs and must be credited either way.

---

## 10. What this doc does not do

- It changes no agent code. `agent.py` and the seat prompts stay untouched until this is agreed.
- It does not install, run, fork, or clone freebuff, and sends it none of our code — as instructed.
- It does not touch `rules.py`, `.githooks/`, or any file another seat currently holds.

---

## 11. Folded in from Tern-25's pass (#745) — each item checked against the source

Tern-25 (claude.ai cloud) read the same source independently and pushed
`claude/tern-25-freebuff-extract` @ `500aebf`, writing to **this same path**. Mine landed first
(`c160ac8`), so rather than land theirs over mine I have folded in the four things it had that mine
did not. Each is checked against the source, not taken on the strength of the claim. The rest of
their four-section doc duplicates §2, §3 and §5 above and adds nothing.

### 11.1 Per-model compaction tied to the provider's cache life — the one addition I rate highest

File: `common/src/constants/compaction-policy.ts`. **Verified verbatim:**

- `DEFAULT_COMPACTION_POLICY` = `cacheExpiryMs: 60 * 60 * 1000` (1 hour), `cacheExpiryMinTokens: 140_000`.
- `DEEPSEEK_FLASH_COMPACTION_POLICY` = 15 minutes / `40_000`, for DeepSeek V4 Flash, "whose front lane is Luminal".
- `compactionThreshold(max) = Math.floor(max * 0.8)` — every trigger fires at **80% of the window**.
- `LEAN_COMPACTION_POLICY` = 110k window with `lean: true`, 1h idle, 40k floor → it fires at 88k.

Their reasoning is the part worth lifting, because it is counter-intuitive: **the idle trigger is a
product knob, not a TTL tracker.** Compaction never prevents the cold prefill after a gap — it only
shrinks it, at the price of dropped tool results — and under an hour it reads as *"the model forgot
everything"*, which they name as a top user complaint. The token floor exists on the same logic:
*"compaction is free in tokens but never in information."* On the DeepSeek lane a cold input token
costs **~40× a cached one**, so halving a cold 60k prefill is a material share of a turn's spend.

Also independently confirmed here: **the per-message transforms alone strip ~87% of a tool-heavy
coding history at every size** — which is where Tern-25's "87%" figure comes from.

**Where it goes:** a per-model `cacheLife` field beside the routing data, and compact after an idle
gap longer than it. It matters exactly for our failure mode — long jobs that pause on rate limits
or while Phil is away. Cheaper companion note: their lean prompt must stay **byte-identical from
step to step**, or the prompt cache stops matching and every step pays full price.

### 11.2 The C# gap is in OUR file — verified in our tree

`src/megazword/repo_map.py:21`:

```python
LANGS = {".py": "py", ".ts": "js", ".tsx": "js", ".js": "js", ".jsx": "js", ".mjs": "js"}
```

and the only regexes defined are `PY` and `JS`. **`.cs` is absent, so `_files()` skips every C#
file — RobinTHood and Spanda produce an empty map.** That is a live defect in our tooling, not a
freebuff idea: the map we built for "models re-read whole files to find their way around" shows
nothing at all for the two products we are actively shipping. Fix: add a C# regex for
class/method signatures, or lift their tree-sitter C# query (`packages/code-map`) if regex proves
too rough. Keep our 1.5k-token map — this is an addition, not a replacement.

### 11.3 Score models on real work before routing to them

`evals/buffbench`: a task is a real past commit — the agent rebuilds it from the commit message, a
judge scores completion and code quality, and the repo's own test command gives pass/fail;
`compare-arms.ts` runs two setups side by side. **Take:** use our own merged commits as tasks for
`scores.py`, so routing learns which free model can be trusted with which job shape. Separately,
`agents/base3-free-*.ts` is one small file per free model over one shared base — a clean pattern for
`docs/FREE-MODEL-ROSTER.md` and `routing.py`.
*(Read by Tern-25; I did not read `evals/` or `agents/base3-*.ts` myself — flagged as relayed.)*

### 11.4 RobinTHood ad and meter rules — Tern-25's read of their `cli/src`, not mine

Attributed and **not independently verified by me**: ad network **Gravity** (`api.trygravity.ai`);
one slot, one ad; every ad labelled **"Ad"**; a **×** hides it for the session; **no empty slot**
when nothing is served; an impression counted when the ad is shown, a click counted before the link
opens; sponsored offers open a **consent screen** and never accept on one click; usage sold in
one-hour sessions with cheap models unmetered, an **unused hour refunded after 5 minutes**, and the
price re-checked before spending; earn-hours by referral (paid when the friend sticks) and bounties;
full access in supported regions, a smaller daily allowance elsewhere and on VPNs.

**Take:** the ad rules are copyable now — label, ×, no empty slot, honest counting — and the hours
meter is a far better shape than RobinTHood's invented "SAVED $" figures. It fits the already-decided
PROD-1 change (show measured answers and time). Hand this list to **Anvil-22**. Gravity itself is a
sign-up: **Phil's call, no sign-up without him.**

### 11.5 Consequence

With §11 folded in, Tern-25's `claude/tern-25-freebuff-extract` branch can be dropped — every
addition it carried is now here, checked. The credits stand either way: the per-model policy, the
C# gap and the ad rules came from that pass.
