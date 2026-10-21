# Archive: branches deleted 2026-10-21

Each was checked with `git cherry origin/main` before deletion, and its tip commit stays
reachable by sha. Reason column says why it is not worth keeping.

| Branch | Tip | Subject | Why it was dropped |
| --- | --- | --- | --- |
| `agy/beta2-2026-10-11` | `b91a2d4` | WIP (unfinished): Orbit-1's duplicate B1 room engine, saved before agy ran out | Orbit-1's DUPLICATE B1 room engine, WIP, saved when agy ran out |
| `claude/beta3-notes` | `c0cdc94` | Beta 3.0 release notes: README "What's new in Beta 3.0", GUIDE adds plan and app install | release-notes draft; docs/RELEASE-NOTES.md supersedes it |
| `claude/beta4-spawn-plan` | `2a7adf5` | Roadmap: free-first, self-improving Hive (Phil's standing direction, 2026-10-12) | docs-only spawn plan; hive_up/hive_resume superseded it |
| `claude/hive-widget` | `4015378` | Hive widget: sending a message wakes the bots; session output goes to hive_widget.log | the widget it describes runs on this box already |
| `codex/b12-model-choice-2026-10-12` | `cafa655` | Add per-task model and effort profiles | per-level model config exists in config.toml [grok.<level>] |
| `codex/b13-default-app-2026-10-12` | `12c2289` | Open dashboard app from bare command | bare `megazword` opens the app on main |
| `codex/cloud-chatgpt-bridge-2026-10-18` | `6dc0549` | Preserve uncommitted cloud-Hive WIP found during worktree audit (as-is) | deliberately not landed: would drop /read and rename MCP tools |
| `codex/cost-aware-selfhosted-ci-2026-10-14` | `2f57bd8` | Record self-hosted CI result and local-first gap | tip commit is docs/STATUS.md +3/-1 - a note, not CI code |
| `codex/night-free-workers-2026-10-14` | `a2b3cfd` | WIP: shelve local Night Shift integration per Phil direction | shelved WIP per Phil's direction |
| `codex/tab-order-2026-10-12` | `c9202fb` | Claim persistent tab order API | claim only; no implementation behind it |
| `grok/floor-announce-2026-10-14` | `072c639` | Add megazword announce so Phil can ping every hive seat once. | megazword announce exists on main via another route |
| `grok/free-floor-2026-10-14` | `20468e8` | Free floor: one desktop, one Terminal, tabs not extra desktops | desktop/tab staffing concept replaced by hive_up + hive_resume |
| `grok/groq-cf-1010-2026-10-14` | `85a449e` | Groq: send via curl so Cloudflare 1010 does not block this PC. | free_apis.py already has _curl_bin/_use_curl; a live probe returns 401, not 1010 |
| `recovery/2026-10-16-tab-order` | `48b3e57` | Preserve unfinished tab-order draft from cleanup audit | preservation branch from the cleanup audit |
| `recovery/2026-10-16-usage-pace` | `c2dc389` | Preserve unfinished usage-pace draft from cleanup audit | preservation branch from the cleanup audit |
| `recovery/2026-10-19-restore` | `8e0a660` | Recovery: take the real tree back onto main without a force push | the main-recovery history; its outcome is on main |
| `seat/router-17` | `20f6e5d` | docs: record routing prototype PR | routing research docs; route-lab landed |
| `seat/word-31` | `949008c` | Preserve reviewed manual listener draft before wake consolidation | manual listener draft, superseded by the live wake listener |

18 branches.
