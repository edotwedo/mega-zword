# Open branches and uncommitted work

**Why this file exists:** Phil, 2026-10-23 - "every day I try to keep things from the day before
but it's too much to remember." This is the one place that answers "what is still unfinished?".
Update it whenever a branch is landed, archived or opened; do not let it become a changelog.

## Committed on 2026-10-23 (worktree audit)

- `cinder/f1c-stale-reads` -> **landed** on main. F1c from `docs/PLAN-hermes-execution.md`: room
  reads now carry their own freshness (`RoomMessages.stale/.age_minutes/.notice`), so a cache-only
  read older than 10 minutes says so instead of silently looking current.
- Forge-22's model-switching docs -> **landed** (`docs/ROADMAP-model-switching.md`,
  `docs/ROADMAP-model-switching-facts.md`; Phase 0 proved `agy -p /usage` is machine-readable and
  `--conversation <id> --model <name>` switches across pools, which unblocks Phase 3).
- `task/word31-wake-delivery` -> **landed** on main: the `wake.ack` alias plus tests pinning that
  acknowledging a message does not consume in-flight newer ones.
- The Forge-22 Dualtooth/Spanda handoff note -> **committed** (was untracked).
- `seat/codex` and `seat/grok` worktrees -> **committed and pushed** (uncommitted edits from
  2026-10-20 that would otherwise have been lost).
- The rules gate was red (P6 applied but never approved) - fixed; `command-code` was reinstalled
  after an interrupted update gutted it.

## Still open

| Branch | Ahead | Files | Last | Recommendation |
| --- | ---: | ---: | --- | --- |
| `seat/cinder-21` | 1 | 1 | 2026-10-22 | archive - the handoff doc is on main |
| `harbor022/hermes-plan` | 2 | 1 | 2026-10-22 | archive - adopted by P4, doc is on main |
| `harbor022/outbox-jam` | 3 | 3 | 2026-10-22 | archive - landed as `6cd909c` |
| `seat/briar-20` | 1 | 7 | 2026-10-22 | archive - M2 landed as `361fdd5` |
| `seat/router-17` | 4 | 5 | 2026-10-17 | review then archive - routing prototype docs |
| `seat/quill-21` | 1 | 3 | 2026-10-19 | archive - superseded by the cmdc API meter |
| `codex/cost-aware-selfhosted-ci-2026-10-14` | 9 | 5 | 2026-10-14 | archive - beta-era |
| `codex/b13-default-app-2026-10-12` | 4 | 17 | 2026-10-12 | archive - re-implemented on main |
| `codex/b12-model-choice-2026-10-12` | 2 | 16 | 2026-10-12 | archive - superseded |
| `codex/tab-order-2026-10-12` | 1 | 1 | 2026-10-12 | archive - `tab_title.py` exists on main |
| `codex/cloud-chatgpt-bridge-2026-10-18` | 2 | 8 | 2026-10-18 | archive - preserved WIP, never continued |
| `claude/beta4-spawn-plan` | 2 | 2 | 2026-10-12 | archive |
| `grok/floor-announce-2026-10-14` | 1 | 5 | 2026-10-14 | archive - `announce` exists on main |
| `grok/free-floor-2026-10-14` | 2 | 11 | 2026-10-14 | archive |
| `grok/groq-cf-1010-2026-10-14` | 1 | 6 | 2026-10-14 | archive - the curl workaround shipped |
| `agy/beta2-2026-10-11` | 2 | 3 | 2026-10-11 | archive - explicitly unfinished duplicate |

**Archive** = record the tip sha in `docs/ARCHIVE.md` with the reason, then delete the branch and
remove its worktree. `docs/ARCHIVE.md` already records ~170 branches this way.

## Stashes (in the main repo)

- `stash@{0}` "Cedar-14 preserve installed local overlay before current main update"
- `stash@{1}` "Easel-11: worktree equal to old main, set aside 2026-10-11"

Both are old; inspect before dropping. Not lost, just parked.

## Untracked, deliberately not committed

- `.codex-remote-attachments/` - Codex session attachments (cache, not source).
- `mz-seats/lumen-20/.wrangler/` - Cloudflare Wrangler cache.
- `mz-seats/codex-test-log/CODEX_JOB.md` - explicitly excluded from commits (Phil, 2026-10-16).
