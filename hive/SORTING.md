# What ships? Draft sort of `src/megazword` (for Phil, 2026-10-28)

Draft by the cloud Claude session (Quill-28). Every bucket below is **my suggestion**; Phil decides
tonight. After that, the move goes to a `megazword vote` and is done as its own job.

- **Ship**: the product. One terminal tool over all your AI CLIs: routing, usage, keys, chat, dashboard.
- **Dev**: a possible Dev edition for power users: multi-agent jobs, night queue, reviews, terminal workspace.
- **Hive**: ours only. Moves to `hive/` and never ships.
- **?** = I'm unsure; it needs Phil's call.

One structural catch: `cli.py` (1,185 lines) registers every command, Hive ones included. The split
means moving the Hive commands out of `cli.py` into a separate `hive` command, not just moving files.

## Ship (50)

| Module | What it is |
|---|---|
| `__init__`, `__main__`, `cli` | The `megazword` command (after the Hive commands move out) |
| `config`, `log`, `filelock` | Settings, log files, file locking |
| `backends`, `routing`, `request_mode`, `rater`, `decision`, `quality`, `escalate`, `failures`, `limits` | Pick the AI, rate the job, retry upward, explain errors |
| `chat`, `tabs`, `tab_sessions`, `compare`, `answers` | Chat, pinned tabs, side-by-side compare, past answers |
| `dashboard`, `desktop`, `appwindow`, `start`, `doctor` | The window, start screen, health check |
| `usage_sources`, `meters`, `pacing`, `usage_guard`, `spot`, `cmdc_quota` | Usage meters and pacing: the core selling point |
| `keys`, `credential_store`, `free_apis`, `free_test`, `ollama`, `openrouter_catalog` | Providers and keys |
| `ledger`, `budget`, `guard` | Credit grants, spend cap, "this AI trains on your data" warning |
| `memory`, `export`, `stats`, `runlog` | Project memory, reports, stats |
| `agent`, `agent_quality`, `andon`, `run_control`, `public_fetch`, `repo_map` | The coding loop and its safety stops |

## Dev edition (14)

| Module | What it is |
|---|---|
| `job`, `job_workers`, `job_cost`, `team`, `scores` | Split a coding job across several AIs and combine the results |
| `review` | Several AIs review one change |
| `night` | Night Shift: work through a queue while you sleep |
| `advise`, `router_lab`, `scout` | Routing advisor, routing lab, finds new free providers |
| `gate` | Land-gate: nothing reaches main until the suite passes |
| `workspace`, `workspace_terminal`, `terminal_input` | Windows Terminal session snapshots and relay |

## Hive only (22)

| Module | What it is |
|---|---|
| `room`, `room_wait`, `mcp_hive`, `claims`, `sentry`, `wake`, `escalate_watch` | The Hive room and waking seats |
| `vote`, `rules` | Ballots and the rules hash |
| `seat`, `floor`, `resume`, `tab_title` | Seats, designations, respawning |
| `task`, `workers` | File leases, worker inboxes |
| `briefing`, `startup`, `memory_index` | Seat startup readings |
| `heartbeat` | Keeps *our* roadmap moving (disabled by Phil) |
| `announce`, `hive_import` | One-shots; `announce` still points at Q, which is now closed |
| `sentinel` | Uptime/security log for Phil's PC and our services |

## Your call (?) (3)

| Module | Question |
|---|---|
| `presence`, `face_identity` | Webcam presence and owner face matching. Is this a product feature, or ours? Privacy-heavy either way. |
| `phone` | Finds a Tailscale address for the phone page. Ship it if customers get a phone view; otherwise Hive. |

Total: 89 modules (`__init__`/`__main__`/`cli` count as three).
