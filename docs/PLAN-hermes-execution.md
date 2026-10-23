# Hermes execution plan (for review, then work)

**From:** Cinder-21 (conductor). **Date:** 2026-10-22.
**Status:** draft for review. Adopted plan of record: `docs/PROPOSAL-beat-hermes.md` (ballot **P4**,
carried 3-0). This file turns P4's pillars into buildable items, owners and proof.
**How to use it:** Phil hands this to his Gemini instance to review and amend; it comes back to
Cinder-21, who keeps it here and hands out the wave-1 items. Section 10 is written for the reviewer.

---

## 1. Decisions locked today (do not reopen without Phil)

1. **Build the whole plan, all pillars** (Phil, 2026-10-22) - not a slice.
2. **Review rule is code-only** (Phil, 2026-10-22): a code change needs a second-bot review; docs,
   config and data files do not. This **rescopes P5** - P5 as cast said "delete the requirement".
   It is re-opened with new wording (section 7) and re-cast. Until it carries, M3 stands.
3. **No rule is added or changed on chat text** - only on a passed ballot (my own correction today,
   after I turned a throwaway remark into a recorded decision).
4. **Distribute across every seat**, including Forge-22 (Gemini - **one instance only**, Phil,
   2026-10-22).
5. **Every seat's instructions tell it to also use megazword** (Phil, 2026-10-22). The CLI is the
   shared tool - routing, review, usage, note/decide, the room, the gate - not each bot's own habits.
   Added to `AGENTS.md` so it loads for every seat at startup.
6. **Harbor022's window is open now** (Phil, 2026-10-22, ~15% left, resets tomorrow). Use it today on
   F1b and the high-risk reviews; do not leave it idle, and do not spend it on volume.

## 2. The team and what each is for (re-read `megazword usage` before each claim)

| Seat | Vendor | Give it | Do not give it |
| --- | --- | --- | --- |
| Cinder-21 | cmdc | Integration, the merge queue, room/liveness code | Long open exploration |
| Briar-20 | Codex | Heavy edits: outbox, locks, installer, gateway | Unscoped destructive runs |
| Nock-21 | Grok | Benchmarks, breadth, the comparison page, hygiene audit | Scripted/automated access (xAI AUP) |
| Harbor022 | Claude | High-risk review (F, E1), the Worker claim parser, plan honesty | Volume |
| Forge-22 | Gemini (**one instance**, Phil 2026-10-22) | Second opinions on memory + brand, model-switching Phase 0 | Bulk background work |

Capacity note: readings on 2026-10-22 were codex ~100%, cmdc 63%, grok 60%, gemini ~1% (Google may
have reset; verify live). The matcher is the command, not this table.

## 3. Waves (sequence; matches P4 section 5, parallelised across seats)

- **Wave 0 - review.** Phil -> Gemini: review and amend this file. No code.
- **Wave 1 - fix our own house.** F1 (the four named holes), F2 (heartbeat + watchdog + daily probe),
  M2 (file locks). Nothing else starts until F1's four holes are closed and tested.
- **Wave 2 - the spine + the moat.** M1 (merge queue), M6 (command grammar), F3 (status page),
  A1 (usage home screen), A2 (routing on by default), A3 (money-saved meter).
- **Wave 3 - the front door.** C1/C2/C3 (warning + cage guide + brand voice), D1/D2/D3/D4 (installer,
  first-run discovery, clean-machine gate test, repo hygiene), resolve Grok/Gemini provider terms.
- **Wave 4 - take their strengths.** E1 (two-way phone gateway), E2 (searchable cross-seat memory),
  E3 (scheduling through the one supervisor), E4 (Hermes as a seat).
- **Wave 5 - prove it and launch.** A4 + B3 benchmarks, the comparison page, code signing, public beta.

## 4. Item detail (each is one claimed task, one branch, landed through the gate)

### Wave 1

| ID | Deliverable | Files | Done when |
| --- | --- | --- | --- |
| **F1a** | Outbox cannot jam. A 4xx (409/403) post is **parked** with its error, not left at the head; 5xx/network still retry; a **busy** queue or cache retries with backoff instead of raising. | `src/megazword/room.py::RemoteRoom.flush` | Fake server returns 409 then 201: the later post lands and the refused one is in `*.parked.jsonl`. Two seats posting at once lose nothing. |
| **F1b** | No phantom claims. The Worker rejects a degenerate item (empty/whitespace after unquoting) and `releasing <item>` clears a quoted item. | `cloud/hive-room/index.js` | Worker test: a `claiming ''` probe registers nothing; a release clears a held quoted item. Phil deploys. |
| **F1c** | Reads cannot go stale silently. The seat-facing read refreshes when a room URL is set; a cache-only read older than N minutes says so. | `src/megazword/room.py::read_messages` + callers | A configured room's cached-only read emits the staleness notice; `room show` is always fresh. |
| **F1d** | The listener cannot lie. The watcher records a monotonic tick (last room id + timestamp) and the health check reads it, not "Ready". | `scripts/wake_watch.ps1`, `src/megazword/wake.py` | Killing the watcher mid-run makes the health check report stale within two intervals. |
| **F1e** | No two seats share one outbox: each seat posts under its own room key, so a queue belongs to one seat. `keys`/`doctor` show which seats have their own. | `room.py::RemoteRoom.__init__`, `keys.py`, `doctor.py` | Two seats post concurrently with no lost post and no shared queue file. |
| **F1f** | The meter cannot herd: a single-flight lock means concurrent `usage` calls cost **one** terminal read and return the same numbers. | `meters.py`, `cmdc_quota.py`, `cli.py` | Five concurrent `usage` calls produce one CLI read and identical output. |
| **F2** | Liveness is observed (M4): per-seat monotonic heartbeat + watchdog + a daily synthetic Phil message that must arrive end to end in a scratch room. | `src/megazword/heartbeat.py` | With fakes: a stale tick raises; the synthetic probe is delivered and acknowledged end to end. |
| **M2** | Work is an object with a lock: `megazword task new --title --files` allocates id + branch + lock; 30-min renewable expiry (P3); hot files never locked; the gate refuses a push touching another open task's file. | new `src/megazword/task.py`, `filelock.py`, `.githooks/pre-push` | In a temp repo: a locked file blocks a second task's push; the lock expires when its heartbeat goes stale. |

### Wave 2

| ID | Deliverable | Files | Done when |
| --- | --- | --- | --- |
| **M1** | One writer to main: a serial merge queue with a **named deputy** (Cinder-21 primary, Briar-20 deputy). | new `src/megazword/queue.py` | Queue takes items in order; the deputy can take the next when the primary is stale. |
| **M6** | Instructions parse: `assign / standdown / stop / vote`; anything else is unanswered with numbered options, and nothing happens. | new `src/megazword/grammar.py` | An ambiguous order performs no action and prints options. |
| **F3** | A status page of **observed** liveness (tick age, last room id, last delivery) - never claimed. | `dashboard.py`, `briefing.py` | Page shows tick age per seat; a dead seat reads stale, not Ready. |
| **A1** | Usage board is the home screen: every plan, every window, reserve, reset, plus free sources left. | `start.py`, `dashboard.html` | Home screen shows all plans and free sources from the live meter. |
| **A2** | Routing on by default: the job goes to the plan with the most room that fits, never below the floor; `--no-route` escapes. | `routing.py`, `cli.py` | A job routes to the roomiest fitting plan; a floor breach is refused. |
| **A3** | Money-saved meter: what each job would have cost at API prices vs what it cost. | `ledger.py`, `stats.py` | `megazword stats` shows dollars saved per job, from the run log. |

### Wave 3

| ID | Deliverable | Files | Done when |
| --- | --- | --- | --- |
| **C1** | The warning is the first screen and the README's first line: what every seat can touch, in one sentence, and "run it in a sandbox". | installer, `README.md` | First screen shows the warning; README leads with it. |
| **C2** | A cage guide: Windows Sandbox, a VM, or a spare user account. A guide, not a feature. | `docs/CAGE.md` | Guide exists, plain steps, no tooling to maintain. |
| **C3** | Brand voice everywhere: fast, loud, no hand-holding, nothing hidden. | user-facing text | A written voice sheet + the top screens follow it. |
| **D1** | One signed installer, no AV warnings, no Python/Node/FFmpeg fetch. | `scripts/install.ps1`, signing | Installs on a clean Windows 11 with 0 AV warnings. |
| **D2** | First run finds the AI CLIs the user already has, working in under 5 minutes. | `doctor`, `start` | A machine with two installed CLIs reaches its first answer in <5 min. |
| **D3** | A clean-machine install test in the gate, so the front door cannot break unseen. | new test, `.githooks/pre-push` | The test fails if install regresses. |
| **D4** | Repo hygiene a stranger can see: short paths, no scratch at root, a size cap per module, tidy root. | repo-wide | A hygiene test asserts the caps and a clean root. |
| **P-TERMS** | Resolve the Grok and Gemini provider terms. | `docs/PROVIDER-TERMS.md` | A written, dated answer per provider, or `[phil]`. |

### Wave 4

| ID | Deliverable | Files | Done when |
| --- | --- | --- | --- |
| **E1** | Two-way phone gateway (Telegram or Discord) into the Hive: Phil posts from his phone, seats answer there. One bookmark, no key lookup. | new gateway module, Worker | A phone message reaches the room and a seat's reply comes back to the phone. **Bot API only - no scraped site posting.** |
| **E2** | Searchable memory shared across seats, built on the P2/A2 index; MemPalace as an optional plug-in. | `memory*.py`, MCP | A cross-seat search returns a sourced hit. |
| **E3** | Scheduling through the one supervisor (M5); no seat schedules itself. | `night.py`, supervisor | All recurring work is registered in one place. |
| **E4** | Hermes as a Mega Zword seat on its own plan (ballot H4 carried). | roster, backends | Hermes answers a real task as a seat, named in the roster. |

### Wave 5

| ID | Deliverable | Done when |
| --- | --- | --- |
| **A4** | Public benchmark: one fixed task set, run through Hermes-on-OpenRouter and Mega Zword-on-subscriptions; publish dollars and scripts. | Scripts + numbers are public and reproducible. |
| **B3** | Planted-bug benchmark: what one Hermes agent catches vs a cross-vendor review. | Published repo + counts. |
| **PAGE** | The comparison page (P4 section 4): every row backed by a script anyone can run, no insults. | Each row's script reproduces its number on a stranger's machine. |
| **LAUNCH** | Public beta, code signing, page live. | A stranger installs and runs it. |

## 5. Distribution (Phil: direct me, I direct the seats)

| Seat | Owns |
| --- | --- |
| **Cinder-21** | Integration; F1c, F3, M1, M6; reviews every diff before it lands. |
| **Briar-20** | F1a, M2, D1, D2, E1 (heavy edits). |
| **Nock-21** | A4, B3, PAGE, D4 (breadth + benchmarks). |
| **Harbor022** | F1b, high-risk review of F and E1, keeps this plan honest. |
| **Forge-22** (one instance) | C3 + E2 second opinions; **model-switching Phase 0** (approved separately) runs as its own track. |

Every item is claimed before work (`megazword room say "<seat>: claiming '<id>'"`), one open claim per
seat, one branch, landed through the gate. **Wave 1 starts now** (Phil, 2026-10-22), alongside Wave 0's
review: Harbor022 and Briar-20 are already windowed, so their items are handed out immediately.

## 6. Guardrails

1. **No platform-ToS automation.** The phone gateway (E1) uses a bot API. Nothing posts to Reddit,
   HN or StackExchange on a burner account. (P4 H3: every published claim has its script.)
2. **No rule from chat.** Section 1.3.
3. **Review is code-only** (section 1.2), once the rescoped ballot carries; until then M3 stands.
4. **Never publish a number we have not reproduced**, or Nous Research reproducing it becomes the
   story.
5. **Keep the live files small** (STATUS under the 8 KB cap, `MEMORY-INDEX.md` regenerated).

## 7. Ballot chores

- **P5 rescope (needed):** current P5 says "delete the non-author requirement" (1 of 3). Reword to
  **"a second-bot review is required for code changes; docs, config and data are exempt"**, then
  re-cast. Phil's decision; the ballot makes it legitimate.
- **Already carried by P4:** H1 strategy, H2 order of battle, H3 reproducible-only, H4 Hermes as a
  seat, H5 phone gateway, H6 rally-car positioning. No new ballot for E1/E4/C - build them.
- **P3 (carried):** M1 deputy + M2 30-minute renewable lock are already in the rules.

## 8. Verification (how we know a wave is done)

- Per item: its own focused test, then the full suite through the gate (currently 2003 passed, 1
  skipped). A code item is not done until a second bot reviews the diff and the gate is green.
- Per wave: the item's "done when" run **by a different seat** than the author.
- Wave 1 additionally: kill the watcher and confirm F1d reports stale; post a 409 and confirm F1a
  parks it.

## 9. Risks

- **M2 locks vs real tasks.** A task can span files nobody predicted; that is why the lock is 30 min
  and heartbeat-renewed (P3). If it still stalls the team, the fallback is locks only on files a task
  declares in advance.
- **A2 stale meters.** Routing on a stale reading sends work to a plan that is out of room; the
  "stale means unknown" rule must gate the choice.
- **E1 fairness.** A gateway that only works from Phil's phone is not "two-way" for a stranger;
  scope it honestly.
- **Gemini capacity.** Forge-22 reads at ~1% on one meter; confirm before assigning it anything past
  opinions.

## 10. For the reviewer (Gemini) - please answer or amend

1. **Order:** would you reorder any wave? Wave 1 is F1 + M2 by design ("fix our own house first").
2. **M2:** are 30-minute heartbeat-renewed file locks workable for tasks that span unpredicted files,
   or is a declared-files-only lock the honest design?
3. **A2:** with a stale meter, should routing refuse and ask, or fall back to the least-used plan?
4. **E1:** Telegram or Discord for the two-way gateway, given Phil's phone and the existing one-way
   Discord mirror?
5. **PAGE:** what would make the comparison page unconvincing to a skeptic, and how do we pre-empt it?
6. **Anything missing** from the pillars that a $1.5B competitor would use against us.
