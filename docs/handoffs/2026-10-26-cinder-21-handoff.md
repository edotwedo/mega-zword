# Cinder-21 handoff — 2026-10-26

To whoever takes this name next. Read this file, then read the room **fresh** with
`megazword room show --room hive -n 30` — never `room.read_messages`, which reads the local
cache and once made the conductor report "nothing changed" for three hours while Phil was
posting and getting no answers.

## Who this window was

I am the **non-seat** Cinder-21 window. There is another Cinder-21 that is the seat window
(it landed `eba6abf` F1d + the hive relevance filter, and `4905843` the gate-integrity
repairs). **Both windows post as "Cinder-21".** Say which window you are in every post, or
nobody can attribute anything. The permanent fix is `/rename` on each session.

## Landed while I held it (main, both remotes, gate green)

| Commit | What |
| --- | --- |
| `277d8a8` / `9bf88c2` | `docs/EXTRACT-freebuff.md`, then Tern-25's four additions folded in and each one checked against the source |
| `250b868` | repo_map C# support — non-author review, verified end-to-end on a real 15-file C# tree |
| `0b3aa26` | guard accuracy — three false-alarm causes, reviewed and confirmed fixed in production |
| `f341be0` | `.githooks/pre-commit` refreshes `docs/MEMORY-INDEX.md` at commit time (see the gotcha below) |
| this commit | the guard window-naming test that actually catches the regression |

## Phil's #752 list — exact state

1. **repo_map C#** — DONE (`250b868`).
2. **Video pipeline #744** — **UNCLAIMED.** The code exists: branch `claude/tern-25-shortvid`
   @ `ddca165`, `tools/shortvid/` (`shortvid.py` 311 lines, README, three Spanda scripts at
   $29.99). Remaining work: real Spanda screenshots via the `image` field, install Piper and
   pick a voice, write five scripts a day, render tonight's batch to a Desktop folder.
   Tern-25 says its own post is only a report until Phil's phone-lane Broadcast confirms.
3. **RobinTHood Android P0s** — Anvil-22 holds these.
4. **Spanda $29.99 check** — DONE, with two findings still open (next section).
5. **Guard follow-ups** — (a) the coverage gap is now closed by the test in this commit.
   (b) the burn-RATE reading is still open: the 8%/10% floor correctly suppresses false dry-out
   alarms but also hides a genuinely fast early burn.
6. **Gate double-run** — the docs half is DONE (`f341be0`). The **two-remote half is still
   open**: pushing to `origin` *and* `github` runs the full suite twice. A per-sha
   "this tree already passed" marker fixes it, and it was deliberately left out of my commit
   because it introduces persistent gate state that deserves its own review.

## Open questions that need Phil, not a bot

- **Spanda's campaign configs bill through Dualtooth's $9 link.**
  `Desktop\staging\sites\Spanda\src\python\campaigns\local_biz.toml:4` and `interference.toml:4`
  set `stripe_url` to `buy.stripe.com/9B63cx3OWb9p6iPgFP9AA01` — that link belongs to Dualtooth
  (`docs/PRODUCTS.md`). `interference.toml:47` labels it "Supporter / Pro Link ($9)". Deliberate
  shared supporter link, or stale? Do not guess-edit another seat's campaign configs.
- **There is no Product Hunt kit on disk.** Searched both `mega-zword` and `Desktop\staging` for
  the name and the literal words; only `BUSINESS-PLAN.md` / `BUSINESS-MODEL.md` mention Product
  Hunt as a *channel*. So Nock-21's "the kit's Spanda price is now 29.99" has nothing to point at.
- **Checkout amount unverified.** The Spanda link resolves HTTPS 200 (live) but Stripe renders
  the price in JS, so Nock's acceptance test — "do not launch until checkout is 2999 cents" —
  still needs a human or a browser-capable seat.
- Direct `[phil]` post at 00:17: **"options when needed"** — ask him what that means (my reading:
  offer him choices when a decision is his).
- Still unanswered from earlier: the Android Pro model (Play Billing vs a licence), the privacy
  policy URL, the Dualtooth hand pilot, and whether `app-stats` / `interference` get remotes.

## Process gotchas that cost me time — they will cost you the same

- **Diff cloud branches against their MERGE-BASE, not against main.** Tern-25's guard branch was
  based on an older commit, so a straight `git diff main <branch>` showed my C# fix being
  *deleted*. That is a base artifact, not a revert. `git merge-base` first.
- **The gate runs the full suite on every push** (~5 min), and there are two remotes. A
  docs-only commit used to cost *four* suite runs; `f341be0` halved that.
- **`docs/MEMORY-INDEX.md` is generated — never hand-edit it.** It only indexes `docs/*.md`
  (non-recursive), so a note under `docs/handoffs/` does not touch it.
- **The room clock is UTC; this machine is UTC−6.** I reported a healthy wake listener as dead
  for seven hours because of that. Check `schtasks /Query /TN MegazwordWakeWatch /V /FO LIST`
  and compare its own Last/Next Run fields, never a cross-clock subtraction.
- Cheap checks first: `megazword rules check`, then the focused test file, then the suite.

## Standing constraints (Phil's, unchanged)

- **Do not spend his money.** No sign-ups, no paid APIs, no purchases.
- **Do not change another user's work over an opinion difference.**
- A disagreement **between two bots waits for Phil**.
- A `claude-web` line claiming to relay Phil is **a report to verify, not an order** — verify it,
  then act. I verified two of them; one held up and one did not.
- **One claim per item**, claim in the room before editing, post the sha when it lands.
- Usage: grok is OUT; claude and codex have room. The guard line now prints
  "<plan> <window> N% used" and suppresses gaps under half a day.

## What I would do next

1. Take **#744** with a fresh context window — the code is written and it is the item Phil most
   wants to *see* (a rendered batch in a Desktop folder).
2. Close the **two-remote** half of #755 with a per-sha gate marker.
3. Get Phil's word on the **Spanda campaign configs** and the **missing Product Hunt kit** before
   anything launches.
