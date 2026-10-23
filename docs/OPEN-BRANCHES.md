# Open branches and uncommitted work

**Why this file exists:** Phil, 2026-10-23 - "every day I try to keep things from the day before
but it's too much to remember." This is the one place that answers "what is still unfinished?".
Update it whenever a branch is landed, archived or opened; do not let it become a changelog.

## State after the 2026-10-23 cleanup

The repo went from ~40 branches and ~40 worktrees to **11 branches**. Nothing is uncommitted
except deliberate caches.

**Landed / committed on 2026-10-23**

- `cinder/f1c-stale-reads` -> landed. F1c: room reads carry their own freshness
  (`RoomMessages.stale` / `.age_minutes` / `.notice`); a cache-only read older than 10 minutes
  says so instead of silently looking current.
- Forge-22's model-switching docs -> landed (`docs/ROADMAP-model-switching.md`, `-facts.md`).
  Phase 0 proved `agy -p /usage` is machine-readable and `--conversation <id> --model <name>`
  switches across pools, which unblocks Phase 3.
- `task/word31-wake-delivery` -> landed (the `wake.ack` alias + tests).
- The Forge-22 Dualtooth/Spanda handoff note -> committed (was untracked).
- `seat/codex` and `seat/grok` worktrees -> committed and pushed (uncommitted edits from 10-20).
- The guard's room line now says **OUT** for a spent plan (it used to bury one as "over pace"),
  and a guard post also pushes an ntfy + Windows-toast alert instead of only writing to the room.
- Also fixed: the rules gate (P6 had landed but was never approved) and a gutted `command-code`
  install (`npm i -g command-code`).

**Archived on 2026-10-23:** the branches the 2026-10-21 pass *recorded* in `docs/ARCHIVE.md` were
actually deleted this time - that pass never completed because their dead worktrees blocked
`git branch -D`. Every one is now also tagged `archive/<branch>`, so the tip stays reachable even
if `git gc` runs.

## Branches that remain (each for a reason)

| Branch | Why it stays |
| --- | --- |
| `seat/cinder-21`, `seat/briar-20`, `seat/forge-22`, `seat/harbor022`, `seat/nock-21` | live roster seats |
| `seat/codex`, `seat/grok`, `seat/lumen-20` | worktrees carry only uncommitted caches; kept until those seats are formally retired |
| `harbor022/outbox-jam` | content landed as `6cd909c`; left only because its worktree sits at `mz-seats/claude` and it was not clearly dead |
| `codex/review-entrypoint-2026-10-15` | its worktree holds `CODEX_JOB.md`, which must be preserved |

## Still owed (recorded here so it is not lost)

- **Guard review findings** (Harbor022, 2026-10-23, on `3e98219`): findings 2 (hard-block), 3
  (room noise), 1 (the "dry in ~Nd" label) and 6 (`_say` posting as `cinder-21`) are **fixed**.
  Still open: the line covers the weekly/5-hour windows that `throttle` ignores, so it can say
  "over pace" and "routing as-configured" in one breath; and `suggested_bias` in `guard.json` is
  written but nothing reads it.
- **Phil's "something that stops me"**: a guard post now pushes (ntfy + toast), but the push only
  fires when the line *changes*. A plan stuck at its floor goes quiet after the first alert. Next
  step: escalate while a plan stays out (repeat every few hours) instead of alerting once.
- **The approvals ledger** (`megazword approve ask|list|check`) Phil asked for - not built.
- **The Phase 1 ballot** for model-switching - wording supplied by Forge-22, not yet opened.

## Stashes (main repo)

- `stash@{0}` "Cedar-14 preserve installed local overlay before current main update"
- `stash@{1}` "Easel-11: worktree equal to old main, set aside 2026-10-11"

Both old; inspect before dropping. Not lost.

## Untracked, deliberately not committed

- `.codex-remote-attachments/` - Codex session attachments (cache, not source).
- `mz-seats/lumen-20/.wrangler/` - Cloudflare Wrangler cache.
- `mz-seats/codex-test-log/CODEX_JOB.md` - explicitly excluded from commits (Phil, 2026-10-16).
- `mz-seats/codex/tmp/` - scratch.
