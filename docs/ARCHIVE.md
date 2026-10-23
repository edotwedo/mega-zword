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

## Fully landed leftovers, deleted 2026-10-21 (Phil: "if it looks like noise, nuke it")

Every one of these had zero patches that were not already on main. Tip sha kept so each stays
reachable. No files, builds or worktrees were touched.

| Branch | Tip | Last subject |
| --- | --- | --- |
| `agy/b1-room` | `24d0e7b` | Build B1 Hive room engine and token budget (Atlas-11) |
| `claude/advise` | `f2938d4` | Smoke: advise check (24); widen compare timing margin |
| `claude/answers` | `e00ac8b` | Save last 50 answers; dashboard shows past answers; fix phone-width overflow |
| `claude/app-window` | `1c3bd81` | F15: megazword dashboard --app (own window), installer -Shortcut, MZ favicon |
| `claude/cancel` | `c43ed0b` | Dashboard: elapsed timer and Cancel button for running jobs |
| `claude/chat-robust` | `77e749d` | Merge remote-tracking branch 'origin/main' into claude/chat-robust |
| `claude/ci` | `61d37cd` | F17: GitHub Actions CI on Windows and Linux (Python 3.11/3.12) |
| `claude/ci-prep` | `d3b992c` | CI prep: Unix fake CLIs executable, pytest finds src/ itself, portable path test |
| `claude/codex-lean` | `b71a30c` | Codex lean one-shots: -c mcp_servers={} under [oneshot] lean |
| `claude/codex-review` | `f275e82` | F21: fixes from reviewing Codex's code (config, free APIs, doctor, installer) |
| `claude/compare` | `20b14fd` | Merge remote-tracking branch 'origin/main' into claude/compare |
| `claude/dashboard` | `15b1359` | Add megazword dashboard: local web page with plan meters, pace, routing, runs, memory and a run box |
| `claude/deflake` | `f9a590e` | F13: deflake timing-based tests (20x full-suite loop: 0 failures) |
| `claude/edit-mode` | `69dfaa5` | Edit mode: keep Grok out on Windows (its path rules don't contain writes) |
| `claude/failure-reasons` | `dd38bbf` | F20: plain-English failure reasons with the fix; stop on dead network |
| `claude/lean-oneshot` | `0e4e602` | F22: lean one-shots for Claude (~half the time, ~1/3 the context) |
| `claude/limit-detect` | `438dc2e` | F10: auto-mark an AI out when it hits its usage limit; lock config writes |
| `claude/live-check` | `0db6bc8` | F14: scripts/live_check.py, an opt-in morning check with real AIs |
| `claude/locking` | `a035e84` | F8: cross-process file lock for log, memory, answers; atomic last_run.json |
| `claude/log-rotate` | `7e825b8` | F5 fixes + dashboard cancel kills the AI process tree |
| `claude/memory` | `d8892c1` | Wire pacing into auto-pick; unknown plan windows never block |
| `claude/merge-b4` | `ea9382e` | write_atomic: unique temp per thread and retry Windows' brief "Access is denied" on replace |
| `claude/meters` | `5eea0be` | F24: one meter summary for start screen, usage and dashboard |
| `claude/night-queue` | `7647fcf` | QUEUE: first night's jobs (J1 refresh list, J2 Android alarm checklist, night status tests) |
| `claude/night-shift-v1` | `5517601` | Merge remote-tracking branch 'origin/main' into claude/night-shift-v1 |
| `claude/no-test-posts` | `3ea23cf` | B6 docs: README for the app launch, Hive room, chat tabs, per-level models, new meters and free AIs |
| `claude/out-cmd` | `f02196b` | Smoke: cover megazword out (17 checks) |
| `claude/plan-out` | `d80fc10` | Add [out] config: mark an AI out of usage until a time; auto-pick and retry skip it |
| `claude/polish` | `6f20d3c` | F19: dashboard notifications, copy buttons, / and Esc shortcuts |
| `claude/projects` | `d0d41b4` | F16: projects (list, dashboard switcher, path-safe names) |
| `claude/quality-check` | `bdd7f8f` | F2: optional answer-quality check (local model second opinion) |
| `claude/remote-dash` | `48db71b` | Dashboard --host for phone access over Tailscale: token required on every request |
| `claude/review-c8-c10` | `af58134` | F25 (partial): review fixes for C8/C10 |
| `claude/review-merge` | `6745c7b` | F12: merge Reed-09 (Codex) review fixes onto main using shared helpers |
| `claude/room-fixes` | `9442e43` | Windows: AI CLIs start with a hidden console (no window flashing per bot turn) |
| `claude/smoke` | `60f0a6d` | Keep LF endings on the Unix fake CLI scripts |
| `claude/start-screen` | `2c68648` | F23: plain 'megazword' shows a start screen |
| `claude/stats` | `44177ae` | Smoke: stats check (20 checks) |
| `claude/stdin` | `4cae7c0` | Grok gets prompts via --prompt-file, not the command line (Windows ~32k cap) |
| `claude/timeouts` | `f65350b` | Smoke: timeout checks (19 checks) |
| `codex/a11y` | `dbc71c7` | Dashboard accessibility: contrast, focus rings, labels, live regions, chart summaries, phone tap targets (Codex Cedar; committed by Kestrel) |
| `codex/b4-hive-ui-2026-10-12` | `ed8d6cb` | Add Hive room dashboard tab |
| `codex/b5-new-look-2026-10-12` | `f689a6e` | Clarify B5 handoff and next lane |
| `codex/b6-app-frame-2026-10-12` | `c4f63fa` | Add app-mode identity header and document Hive controls |
| `codex/beta2-2026-10-11` | `d400e38` | Fix Beta 2 launch permissions and hand controls to lead |
| `codex/camera-presence-fix-2026-10-14` | `1453fe1` | Fix seated face detection for return briefings |
| `codex/chat` | `a6a4c64` | Add megazword chat: interactive session with context and slash commands (Codex) |
| `codex/cleanup-2026-10-16` | `80cbdc5` | Record Sentinel-only monitoring exception |
| `codex/console-layout-2026-10-15` | `a0ceb9f` | Record console installation and release claim |
| `codex/console-popups-2026-10-13` | `80d6cc7` | Hide Windows process cleanup consoles |
| `codex/doctor` | `3d22a9f` | Add megazword doctor and scripts/install.ps1 (Codex reed09; committed by Kestrel) |
| `codex/export` | `719025d` | megazword export: Markdown report of a project's decisions, notes, answers and runs (Codex Alder; committed by Kestrel) |
| `codex/free-agent-loop-2026-10-13` | `709954d` | Coding loop: strip keys from test env and scrub output, glob/timeout/bad-reply fixes, write cap, Cloudflare 400 + Gemini 429 handling (Grok review, Codex) |
| `codex/free-apis` | `41e843e` | Free API backends: OpenRouter and Groq (OpenAI-compatible, key from env, not routed by default) (Codex Astra; committed by Kestrel) |
| `codex/free-catalog-2026-10-13` | `d7f3744` | Kimi, DeepSeek, Qwen-Coder via OpenRouter; coding loop fails over to the next free AI mid-run (Codex) |
| `codex/free-completion-2026-10-14` | `fc442a2` | Remove trailing blank lines from delivery records |
| `codex/free-model-stress-2026-10-14` | `9fb0ea2` | Add Phil setup map |
| `codex/free-pacing-2026-10-13` | `4de38af` | Free bots: per-provider pacing, test-quality gate (rejects assert True), optional reviewer (Flint-13, Codex) |
| `codex/free-provider-repair-2026-10-14` | `03eef2b` | Prioritize free providers across routes |
| `codex/gemini` | `697c485` | Gemini CLI backend: stdin prompts, plan (read-only) mode, never in edit mode, not routed by default (Codex Mica; committed by Kestrel) |
| `codex/guide` | `19a86ac` | docs: record dashboard access clarification |
| `codex/help-polish` | `3c5d09b` | CLI polish: grouped --help with examples, one-line errors for bad input, start screen fits 80 cols (Codex Aster; committed by Kestrel) |
| `codex/night-repair-2026-10-14` | `cdc148b` | Record Night Shift planner integration validation |
| `codex/pacing` | `d92aa10` | Add reset-aware pacing module (Codex) |
| `codex/parallel-workers-2026-10-14` | `213dd1c` | Run planned coding pieces in parallel isolated worktrees |
| `codex/phone-access-2026-10-12` | `0a3452e` | Add checked Tailscale launcher for phone dashboard access |
| `codex/readme-cost` | `a29fafa` | README for the public; rough est_tokens per run in log, usage and dashboard (Codex Astra; committed by Kestrel) |
| `codex/return-briefing-2026-10-14` | `aa80cd6` | Add session return briefings with optional local camera presence |
| `codex/review` | `7368a34` | Fix dashboard job races, cancellation, validation and saved-answer concurrency |
| `codex/review-entrypoint-2026-10-15` | `eaf1f9a` | Record morning runner stderr fix |
| `codex/review-grok-b14-2026-10-12` | `c8661fa` | Fix Z.ai API data-use label and refresh handoffs |
| `codex/room-test-fix-2026-10-13` | `7313044` | Room test: expect one reply now that bot @mentions don't chain (29af82c) (Codex) |
| `codex/run-controls-2026-10-14` | `3bf2824` | Fix cooldown intervention replay, precise retry timing and hard cancel |
| `codex/sandbox-path-2026-10-13` | `1e66005` | Codex on Windows: drop Store PowerShell from PATH so its sandbox can run shell commands (Codex) |
| `codex/settings` | `270e251` | WIP settings panel (Codex Mica, stopped by usage limit; committed by Kestrel) |
| `codex/source-grounded-self-review` | `50e1b68` | Record Self-Review deployment and release worker claim |
| `codex/tab-sessions-2026-10-13` | `61e5aff` | Tab sessions: keep answers when no session id; resume carries project context (Grok review fixes, Codex) |
| `codex/tencent-first-2026-10-16` | `62120e6` | Integrate six Tencent free trial models |
| `codex/terminal-workflow-2026-10-15` | `c0a1cbd` | Claim grounded self-review and Unicode output repair |
| `codex/test-log-2026-10-14` | `187fc74` | test: cover log append and protected trimming |
| `codex/usage-refresh-display-2026-10-14` | `c660a26` | Show each usage window and timestamp live Codex readings |
| `codex/windows-launcher-repair-2026-10-14` | `95a81b9` | Claim Windows launcher repair |
| `codex/worker-review-fixes-2026-10-14` | `cfd55fc` | Fix worker pytest confinement, source imports and per-piece settings |
| `fix/claim-guard` | `f647e0b` | Note Worker claim check awaits Phil's redeploy |
| `free/tests-answers-2026-10-13` | `4de38af` | Free bots: per-provider pacing, test-quality gate (rejects assert True), optional reviewer (Flint-13, Codex) |
| `free/tests-filelock-2026-10-13` | `b8f5a6b` | Tests for filelock.py, written by gemini-api (free) through the built-in coding loop |
| `free/tests-log-2026-10-13` | `4de38af` | Free bots: per-provider pacing, test-quality gate (rejects assert True), optional reviewer (Flint-13, Codex) |
| `free/tests-rater-2026-10-13` | `4de38af` | Free bots: per-provider pacing, test-quality gate (rejects assert True), optional reviewer (Flint-13, Codex) |
| `gemini/beta2-2026-10-11` | `153e5bf` | start_beta2.ps1: one worktree + Windows Terminal tab per AI, handoff prompt pre-typed |
| `grok/agy-empty-success` | `4dfe7b8` | Treat agy empty SUCCESS / tool auto-deny as a failed run |
| `grok/b14-free-ais` | `295b658` | STATUS: B14 merging to main (Phil's call) |
| `grok/b7-review-2026-10-13` | `d6e38e3` | B7 review findings 2026-10-13 (Claude overnight) |
| `grok/beta2-2026-10-11` | `55fa971` | B9: Sentinel URL checks, ntfy, healthchecks, install |
| `grok/effort` | `b989d85` | Handoff: Grok stopped for the night; grok/effort is ready to merge. |
| `grok/escalate` | `b602f07` | Add escalate-on-failure and a local Ollama backend. |
| `grok/floor-2026-10-12` | `79ec4cc` | Add project MCP config so Claude Code loads hive_read/say/wait |
| `grok/floor-presence-2026-10-13` | `75f7dd2` | feat: floor Heard line and hive_up MEGAZWORD_SEAT |
| `grok/free-answers-2026-10-14` | `7e5e6db` | Merge pull request #54 from edotwedo/codex/free-completion-2026-10-14 |
| `grok/hive-resume-2026-10-14` | `aa35567` | Merge pull request #58 from edotwedo/codex/run-controls-2026-10-14 |
| `grok/linux-tests-2026-10-12` | `f9c4c40` | Linux CI: native CLI-guard path; stop patching os.name |
| `grok/mid-job-pace-2026-10-14` | `ac054fe` | Merge pull request #44 from edotwedo/grok/parallel-workers-2026-10-13 |
| `grok/night-free-first-2026-10-14` | `9b81a98` | Night Shift: free APIs run without a meter |
| `grok/night-kill-tree-2026-10-14` | `e05d9fb` | Prove Night Shift job cap kills the whole CLI tree |
| `grok/night-status-guide-2026-10-13` | `b39d7d4` | docs+test: night status GUIDE bullet and status/resume tests |
| `grok/overnight-2026-10-13` | `a4dbfc9` | Tests: gemini-flash-latest default; hidden Windows console |
| `grok/overnight-b7-docs-2026-10-13` | `519a5dc` | B7 docs: MCP in GUIDE/FLOOR, STATUS cleanup, python -m megazword |
| `grok/overnight-b7-low-2026-10-13` | `016ff8b` | B7 L: hive_read n=0, initialize version, atomic snapshot, hive_say mention warning |
| `grok/overnight-beta3-notes-2026-10-13` | `1bc35a6` | docs: Beta 3.0 release notes (no tag) |
| `grok/overnight-ci-ubuntu-2026-10-13` | `98ff1ec` | CI: pin Ubuntu 24.04 before ubuntu-latest becomes 26 (B7 #33) |
| `grok/overnight-codex-2026-10-13` | `f019d64` | Windows: AI CLIs start with a hidden console (no window flashing per bot turn) |
| `grok/overnight-conductor-2026-10-13` | `ebbda5f` | Floor: suggest_seat conductor + floor suggest command |
| `grok/overnight-dash-floor-2026-10-13` | `51c9263` | dashboard: floor object in state JSON |
| `grok/overnight-dash-floor-ui-2026-10-13` | `561c55a` | dashboard Home: Floor ready + seated names |
| `grok/overnight-docs-2026-10-13` | `6b6fafe` | Docs: floor suggest bulk/edit/decide/review |
| `grok/overnight-doctor-floor-2026-10-13` | `b89b010` | doctor: point at megazword floor / floor suggest |
| `grok/overnight-f25-a11y-2026-10-13` | `4a43852` | merge main into F25 a11y |
| `grok/overnight-floor-ready-2026-10-13` | `a002da0` | Floor ready needs a seated CLI; bots cannot say as phil |
| `grok/overnight-floor-status-2026-10-13` | `8c8ae94` | STATUS: 2026-10-13 overnight, PRs 11-16 on main, floor ready |
| `grok/overnight-floor-zero-2026-10-13` | `b23fbd1` | floor: honor -n 0 and --timeout 0; bad --room is one line (B7 #10 #11) |
| `grok/overnight-guide-b7-2026-10-13` | `c088d1e` | GUIDE: Mistral on easy route, zai does not train; STATUS lead Quill-12 |
| `grok/overnight-guide-doctor-2026-10-13` | `9f75aa6` | GUIDE doctor floor line; floor suggest edge tests |
| `grok/overnight-help-floor-2026-10-13` | `8afd8ce` | help: floor suggest one-liner |
| `grok/overnight-help-mcp-2026-10-13` | `b98e8e7` | cli: move mcp under Set up; raise dashboard test timeout |
| `grok/overnight-hive-floor-line-2026-10-13` | `3e1dd27` | dashboard Hive: same Floor ready + seated line as Home |
| `grok/overnight-hive-wait-2026-10-13` | `334e4ac` | hive_wait/floor wait: after=N so messages between read and wait are not missed |
| `grok/overnight-hiveup-2026-10-13` | `f890239` | hive_up: keep-working prompt; print floor suggest |
| `grok/overnight-http-403-2026-10-13` | `939608b` | HTTP 401/403: plain auth errors, never leak the key |
| `grok/overnight-mcp-cli-2026-10-13` | `85988be` | CLI: megazword mcp runs the Hive stdio server |
| `grok/overnight-mcp-json-2026-10-13` | `0b60178` | mcp.json: no machine paths, no hardcoded seat |
| `grok/overnight-mcp-robust-2026-10-13` | `45e2935` | MCP: batch items isolated, negative Content-Length, wait cap 300s |
| `grok/overnight-mcp-stdout-2026-10-13` | `1269d09` | mcp CLI: route stray stdout to stderr, pass raw buffer to serve (B7 #9) |
| `grok/overnight-suggest-auth-2026-10-13` | `c08e1a0` | floor suggest: skip seats whose latest run failed auth (B7 #4) |
| `grok/overnight-userenv-2026-10-13` | `7d3c92a` | Windows: fill missing API keys from User environment |
| `grok/parallel-workers-2026-10-13` | `ae58447` | merge main into grok/parallel-workers-2026-10-13 |
| `grok/room-phil-mentions-2026-10-13` | `87a987c` | fix: Hive one-shots answer Phil once; bot @mentions do not chain |
| `grok/wall-timeout-flake-2026-10-14` | `fc054af` | Relax wall-timeout float compare |
| `old` | `6094358` | gate: clear git's environment before running the suite |
| `seat/alder-16` | `f22a562` | Document installed and verified automatic Codex names |
| `seat/beacon-17` | `d9f6933` | test_claims: give the race-check fixture a live timestamp (fixed date went stale after 24 h) |
| `seat/claude` | `1f9fec4` | rules: delete the old rule set; replace it with choke points |
| `seat/codex` | `f1fd1c9` | docs: record that the site deploy is stopped on purpose |
| `seat/escalation-19` | `f4e3955` | Add one-pass escalation for unanswered Hive calls |
| `seat/fathom-19` | `dd36b5d` | Claims: only a leading quoted name is an item (a quotation made a phantom claim) |
| `seat/grok` | `acec0d0` | Seats: a Command Code tab can hold a seat (Phil, 2026-10-19) |
| `seat/juniper-16` | `c414efb` | Repo map: megazword map ranks a repo's key symbols for prompts (roadmap #5, module) |
| `seat/juniper-16-free` | `cf975bc` | Heartbeat: atomic lock, fast-forward only, 2 completed reviews, no merge of clipped diffs |
| `seat/lumen-20` | `74d7ec7` | backends: one Google CLI path - agy only, retired gemini fallback removed |
| `seat/moss-17` | `1cb0332` | fix: refresh cloud Hive room in MCP readers and waits |
| `seat/sorrel-12` | `bcb5fae` | scripts/nudge.ps1: wake an idle seat by typing into its Windows Terminal tab; only if that AI has more than 15% usage left (Phil) |
| `seat/word-28` | `4b8a471` | Record installed and deployed grok-web identity verification |
| `seat/word-29` | `7ffd70e` | Integrate cmdc live quotas and human-selected work ownership |
| `sorrel/room-fixes-merge` | `23965ac` | Merge overnight PRs onto install copy |
| `task/andon-8` | `8bedc68` | Add andon cord to pause agent jobs at step boundaries |
| `task/powerwall-reserve` | `caf4be3` | Show per-AI reserve and spendable usage (roadmap #7) |
| `task/restart-window-19` | `61181b1` | Stop agent jobs after three failures in a ten-minute window |
| `task/roadmap-10` | `b89cf1c` | Add room claim tracking and WIP cap |
| `task/word31-wake-delivery` | `8da4eb2` | Acknowledge wake messages only after terminal delivery |

157 branches.

## 2026-10-23 (second pass)

Most of the 2026-10-21 list above had never actually been deleted - the branches were still
checked out in dead worktrees, so `git branch -D` refused them. Those worktrees were removed and
the branches deleted. Each is now ALSO tagged `archive/<branch>`, so the tip stays reachable even
if `git gc` runs (the "reachable by sha" promise above was fragile on its own).

| Branch | Tip | Subject | Why it was dropped |
| --- | --- | --- | --- |
| `harbor022/hermes-plan` | `62a990d` | docs: Hermes plan - rally car positioning, no security build (Phil) | adopted by ballot P4; the doc is on main |
| `seat/quill-21` | `918f5df` | usage: Command Code meter, read from its own transcripts (spend, not credits) | superseded by the cmdc vendor-API meter |
| `cinder/guard`, `cinder/f1c-stale-reads`, `m2-integration`, `forge22-facts`, `word31-wake` | - | integration scaffolding | each was fast-forwarded into main; nothing unique |
