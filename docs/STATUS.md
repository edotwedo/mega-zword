# Status

**Active: Larch-11, 2026-10-12 04:24 PT: B5 New look, branch `codex/b5-new-look-2026-10-12`.** Main already contains B12/B13/B15; doing B5, then B4 and B6. Calendar B10/B11 remain parked. Room summaries post to Q only with `--post`.
**Version:** Beta 1, `0.1.0b1`, tagged `v0.1.0-beta.1`. Main has moved on since (live usage meters, widget).
**Lead:** Tally-11 (Claude cloud chat) took Kestrel's seat on 2026-10-12 (Phil lost Kestrel's chat): owns main, merges and assignments. Light lead, because Claude usage is tightest. Phil's direct requests to any bot also go to main.
**Last updated:** 2026-10-12 04:24 PT by Larch-11: claimed B5. Usage before work: Codex 31% of 5-hour / 49% weekly; Claude 30% of 5-hour / 52% weekly; Grok 15% weekly; Gemini out until Oct 18.
**Usage first (Phil's rule):** run `megazword usage` before and after each step. Every plan says which AI does which part.

## Where things live
- **GitHub, `edotwedo/mega-zword`, branch `main`:** the only real copy. If it isn't pushed here, the next AI can't see it.
- **Phil's PC, `C:\Users\mrmar\mega-zword`:** Phil's working copy of main, and where `megazword` should be installed from. Run `git pull` there before starting.
- **Phil's PC, `C:\Users\mrmar\mz-b2-*` folders:** active Beta 2 worktrees; keep them. Check older worktrees for uncommitted/unmerged work before removal. Install only from `mega-zword`, never a worktree.
- **Phil's PC, `~\.megazword\`:** Mega Zword's own data: `config.toml`, `log.jsonl` (run log), answers and memory. Never committed.
- **Logins Mega Zword reads (never committed or printed):** `~\.claude\.credentials.json` (Claude meter), `~\.codex\sessions\` (Codex meter), the `agy` login (Gemini).
- **Hive coordination:** Q, `edotwedo/workshop` PR #33. Mega Zword's own state stays in this file.


## Next (cold start, 2026-10-11 night plan)

From current main: **Step 1 done** (`grok/agy-empty-success`): agy exit 0 with blank/SUCCESS stdout or a tool denial on stderr is ok=false. Next Grok from this branch or main after merge: **step 2 B15**. Codex, own branch, B5 then B4/B6/B13; do not touch routing. Claude after Sun 10:00 PM PT merges only. Gemini nothing until 2026-10-18 15:57 PT. Do not post room summaries to Q.

## Next up (from Tally-11, 2026-10-11): done
All five Beta 1 PC steps are done: reinstalled from main (0.1.0b1), Claude meter readable, Gemini verified live (`agy` answered in plan mode), Beta 1 tagged. Older worktree folders were not certified safe to remove; check each before cleanup.

## Beta 2 lanes (reassigned 2026-10-11 by usage room; spec: SPEC.md "Beta 2", sections R, T, D, S, C)
Each lane has a handoff in `docs/handoffs/2026-10-11-*.md` with everything needed to start cold.
**Lane update (Tally-11, 2026-10-12; handoff `2026-10-11-gemini-lane-moved.md`):** Gemini/agy is at 100% in both pools until Oct 18; park B10/B11. Codex takes B12, then B15, B13, B5, B4, B6. Grok round 2 skips B10, fixes the agy empty-answer bug, reviews B7 and B1, and updates STATUS. B14 and Grok B3/B8/B9 plus Antigravity B1 are already on main. Finish and push each item before starting another. Claude (Tally-11) is lead and merges/reconciles lanes.
Rules: put your name on an item here, own branch, small pushes, tests + smoke pass, no paid calls in
tests, hand finished branches to the lead (Tally-11) to merge; post the branch name in Q. Lane empty? Take the next
unclaimed item from another lane.

Usage at assignment (5h/week % used): Claude 59/31, Codex 12/30, Grok -/0 (new week), Gemini -/3,
Antigravity Claude/GPT pool -/0.

Grok (available now; Oct 17 is its weekly reset) -> `docs/handoffs/2026-10-11-grok.md`:
- **R1 (Nimbus-12, 2026-10-12): done.** Table under B14. Larch-11 cross-review found and fixed the Z.ai API training label on `codex/review-grok-b14-2026-10-12`.
- **B3 Tabs backend (Nimbus-12, 2026-10-12): done.** `tabs.json`, per-tab AI/project/history,
  dashboard API list/create/rename/close/send. Codex B4 can wire the UI.
- **B8 Sentinel collector (Nimbus-12, 2026-10-12): done.** Event-log reader (reboots,
  logins, network), `sentinel.jsonl`, `megazword sentinel status|log`, dashboard panel.
  Fake event data in tests; no admin needed to run tests.
- **B9 Sentinel alerts (Nimbus-12, 2026-10-12): done.** URL checks, ntfy after 2 failures
  and on recovery, healthchecks.io ping, `megazword sentinel install --yes` (Phil
  approves the task), GUIDE.md one-time setup. Not installed on this PC yet.

Antigravity Claude/GPT pool (Atlas-11; B1 done on branch agy/b1-room) -> `docs/handoffs/2026-10-11-antigravity.md`:
- B1 Room engine (DONE, 2026-10-11, Atlas-11): `src/megazword/room.py`, CLI `megazword room
  start|stop|say|show|post-summary`. Branch `agy/b1-room` ready for lead to merge.
  Tests: 541 passed, smoke 31/31. Token-budget rules verified.

Codex (Larch-11) -> `docs/handoffs/2026-10-11-codex.md`:
- First item done: board saved in [coop-interest PR #3](https://github.com/edotwedo/coop-interest/pull/3);
  Oct 7 launch stash recovered in [workshop PR #50](https://github.com/edotwedo/workshop/pull/50).
- B5 New look (SPEC "D. New look"): Windows 11 style with the 1337 accents;
  sidebar tab strip ready for B3/B4. Keep C9 accessibility. Screenshots at
  desktop and phone widths.
- B4 Hive tab UI: room stream, Phil's input box, Start/Pause/Stop, primary
  project, who is talking, turns left. **Room API ready (Tally-11, 2026-10-12):** GET
  `/api/room?room=hive` -> `{room, running, primary, turn_count, turn_cap, last_speaker, messages[]}`;
  POST `/api/room/say {text}`, `/api/room/start {turns?, project?}` (runs turns in a background
  thread), `/api/room/stop`. All need the usual X-MZ-Token. Poll GET every few seconds while running.
- B6 Custom title bar and icons for `--app`; GUIDE.md and README for tabs and the room.
- **B12 done (Tally-11, 2026-10-12, Codex was idle):** `[claude|codex|gemini.<level>]` model + effort
  in config.toml, applied on every route like Grok's; shown in the run line and in `doctor`. Flags checked
  against the real CLIs on Phil's PC. Settings panel left for B5. Original spec: per-task model choice for every AI (extends Grok's `[grok.easy|medium|hard]`): add
  `[claude.<level>]`, `[codex.<level>]`, `[gemini.<level>]` with model + effort. Flags: `claude --model
  --effort`, `codex -m` and `-c model_reasoning_effort=...`, `agy --model --effort`. Unset level =
  that CLI's own default (keep Phil's Codex model unless he sets one). Show the choice in the run
  line. Optional: Antigravity's Claude/GPT pool as a fifth AI (`agy --model <claude/gpt id>`).
  Settings panel + doctor support. Tests with fakes. Gemini reviews; a Claude lead merges.
- **B13 done (Tally-11, 2026-10-12, merged 9c19570).** Plain `megazword` opens the app (Phil, 2026-10-11): with no command, launch `dashboard --app`
  detached and print one line saying so; keep the text start screen as `megazword start` (and when
  stdout isn't a terminal, or `MEGAZWORD_NO_APP=1`, keep today's start screen so tests and scripts
  don't open windows). Update `--help`, GUIDE.md, tests.
- **B14 More free AIs (Nimbus-12, merged to main as `295b658`):** optional
  backends beside OpenRouter/Groq in `free_apis.py` (OpenAI-compatible HTTP, key from env, never
  routed by default, shown in `backends`/doctor, per-provider request counts as their meter).
  **Use the table below; do not invent extra quota numbers.**
  Skip: Perplexity (no free API), Qwen Code OAuth (ended 2026-04-15), GitHub Models (closed),
  Cerebras (now a 30-day $5 credit).

### R1 free-tier check (Nimbus-12, 2026-10-12)
Read from each provider's own pricing/terms pages today. **Several Gmail/email accounts to stack free quota: do not build.** None of these terms allow Mega Zword to rotate extra personal accounts to multiply the free pool.

| Provider | Today's free limit | Signup | Trains on our data? | Several accounts (one person)? |
|---|---|---|---|---|
| **Cloudflare Workers AI** | **10,000 Neurons/day** on Workers Free and Workers Paid; resets 00:00 UTC. Over that needs Workers Paid ($0.011 / 1,000 Neurons). Some models need Paid or AI Gateway credits: Kimi K2.6 / K2.7-code, GLM-5.2 / 5.3 / 5.3-flash, DeepSeek v4. Still free-catalog: Kimi K2.5, Qwen3, gpt-oss-120b, Llama 3.3 70B. Text gen ~300 req/min (Paid-only models 20/min). | Cloudflare account (Phil has one). Account id + API token. No card for Workers Free. | **No (default).** Service-specific terms: "Unless otherwise agreed, Cloudflare does not use any Customer Content to train generative AI tools." | Cloudflare now lets one login create extra **accounts** (dashboard New Account) for project/team split, independently billed. That is not a license to farm extra daily Neurons with throwaway emails; abuse is blocked. **One Cloudflare account is enough.** |
| **Z.ai GLM Flash** | **GLM-4.7-Flash, GLM-4.5-Flash, GLM-4.6V-Flash listed Free** (in/out/cached). GLM-5.3-Flash is **paid** ($0.15 / $0.50 per 1M). Rate limits are account-side, not printed as a monthly token cap on the price sheet. | Z.ai account + API key. | **Individuals: yes.** Terms IV.3.a: for individual users they process User Content "to improve our existing Services and/or to develop new products," including "developing and improving our machine learning and artificial intelligence technologies." **API enterprises/developers: no unless they opt in** ("we will not use your User Content for developing or improving Services unless you explicitly agree"). | Campaign rules: "Each natural person may only use **one platform account**." Coding Plan is "tied to a single account" and "You shall not share your account." Circumventing security measures is banned. **Do not stack Gmails.** |
| **Google AI Studio / Gemini API** (not agy) | Many Flash models **free of charge** within project rate limits, including Gemini 3.8 Flash. Google **does not publish** free-tier RPM/TPM/RPD on the pricing page (Sept 2026); numbers live in AI Studio per project. Grounding Search is not on the free API tier for Gemini 3.x. | Google account; AI Studio API key. No card for Free. | **Yes on unpaid quota.** Pricing page: "Content used to improve our products." Terms: "When you use Unpaid Services, including… Google AI Studio and the unpaid quota on Gemini API, Google uses the content you submit… and any generated responses to provide, improve, and develop Google products… and machine learning technologies." "Do not submit sensitive, confidential, or personal information to the Unpaid Services." Paid (Cloud Billing on the project): not used to improve products. EEA/UK/CH unpaid follows Paid data rules. | Google APIs Terms §2.d: "You agree to, and **will not attempt to circumvent**, such limitations." Gemini Additional Terms: unpaid Studio/API is Unpaid Services. Staff on the Antigravity forum (consumer AI Pro, same Google identity rules): cycling several accounts to pool quota is a ToS violation. **Do not stack Gmails. One API key / one project.** |
| **NVIDIA NIM** (build.nvidia.com) | **No published credit dollar amount on the NIM docs today.** Official line: NVIDIA Developer Program members have **free access to hosted NIM API endpoints for prototyping**; downloadable NIM for research/dev/test on up to 16 GPUs; **production needs NVIDIA AI Enterprise**. Product page: "unlimited prototyping" / "Start Prototyping for Free." Per-model rate limits live in the catalog UI, not a single public RPM/RPD table. | NVIDIA Developer Program account (email; phone verification is commonly required). No card for the prototype endpoints. | **Hosted prototype endpoints: NVIDIA says data is not used for model training.** Product page: "Ensure your data isn't used for model training." NIM *containers* may collect telemetry (settings/usage/hardware) unless `NIM_TELEMETRY_MODE=0`. | Developer Program access is a **personal** non-production license. No NIM pricing page authorizes extra accounts to multiply hosted quota. **Do not stack emails.** |
| **Mistral** (was "Experiment") | Now called **Free mode** (default). Help center: lowest RPS / tokens-per-minute / **tokens-per-month**, "intended for evaluation and prototyping." **The old ~1B tokens/month figure is no longer published**; live numbers are on Admin → Limits. The $10/month API-credit line was removed from the pricing page (~2026-10-07). No card to create a Studio API key. | Mistral account; Studio API key (not a Vibe Code CLI plan key). | **Yes on Free mode, unless Phil opts out.** Help: "As stated during subscription, we may use your data (input and output) to train our artificial intelligence models." Opt out: Admin → Privacy → disable **Anonymous improvement data**. Preview/Labs models can still train even with opt-out (Commercial ToS). Goes in with B15 `trains_on_data`. | Limits are **organization-level** across workspaces. No published permission to multiply Free mode with extra emails. **Do not stack.** |

Sources (opened 2026-10-12): [Cloudflare Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/) (updated 2026-10-09); [Cloudflare Workers AI service terms](https://www.cloudflare.com/service-specific-terms-developer-platform/); [Z.ai pricing](https://docs.z.ai/guides/overview/pricing); [Z.ai Terms of Use](https://docs.z.ai/legal-agreement/terms-of-use) (2026-04-14); [Gemini Developer API pricing](https://ai.google.dev/gemini-api/docs/pricing); [Gemini API Additional Terms](https://ai.google.dev/gemini-api/terms) (effective 2026-03-23); [Google APIs Terms](https://developers.google.com/terms) §2.d; [NVIDIA Run NIM Anywhere / Pricing](https://docs.api.nvidia.com/nim/docs/run-anywhere); [NVIDIA NIM product page](https://www.nvidia.com/en-gb/ai-data-science/products/nim-microservices/); [Mistral rate-limit help](https://help.mistral.ai/en/articles/698531-why-am-i-hitting-api-rate-limits-and-how-do-i-increase-them); [Mistral training help](https://help.mistral.ai/en/articles/347617-do-you-use-my-user-data-to-train-your-artificial-intelligence-models).

**B14 implementation notes:** Cloudflare, Z.ai Flash (free models only), Gemini API unpaid, NVIDIA NIM prototype, Mistral Free mode. Mark Gemini unpaid and Mistral Free mode `trains_on_data=true` (Mistral first for repetitive jobs per B15). The Z.ai Developer API terms say submitted content is not used to train unless the developer opts in; do not mark it as training by default. Cloudflare and NVIDIA hosted NIM default off. Env keys only; never default-routed.
- B15 Light rules for AIs that train on our data (Phil, 2026-10-11, revised the same day: "lightest
  setting"; first user: Mistral Experiment). Any backend marked `trains_on_data = true`:
  1. **Routed normally, and first in line for small repetitive jobs.** Add it to the front of the
     `easy` route and let the room/Hive hand it bulk chores (renames, boilerplate, test stubs, doc
     cleanup, summaries, reformatting, first drafts). Bigger or design work keeps the usual route.
  2. **One light guard:** before sending, drop obvious secrets (API keys, tokens, passwords, private
     keys, `.env` values) and never attach files from `~\.claude`, `~\.codex`, `~\.grok`,
     `~\.megazword` or private folders. That's the same care every bot already takes.
  3. **Edit mode is allowed** like any other AI. The sandbox (Windows Sandbox or a throwaway folder) is
     an option (`--sandbox`) for big batches, not a requirement.
  4. Normal review, same as the other bots. Runs are logged with a `trains_on_data` flag.
  Tests with fakes; never call the real provider in tests.

Gemini (lots of room; agy) -> `docs/handoffs/2026-10-11-gemini.md`:
- B10 Calendar read: `[calendar] ical_url`, `megazword calendar today|week`,
  Home panel, today's schedule in the room prompt. Tests with a sample .ics.
- B11 Calendar write and alarms: Google OAuth desktop login, add events,
  reminders, Windows notification and ntfy push.
- B7 Review pass: review B1-B6, B8-B11 as they land; findings in STATUS.

Claude (tightest; light lead only) -> `docs/handoffs/2026-10-11-claude-lead.md`:
- Review and merge finished branches; keep STATUS and the lanes true.
- B2 Lessons + summaries: **done** (Tally-11, 2026-10-11), see Done.

## Current cross-lane sequence (Tally-11, 2026-10-11 22:30 PT)
1. Grok B14 and R1 are done; B14 is on main. The agy empty-answer fix is merged.
2. Codex: B12, then B13, B5, B4, B6. Reviews Grok's B15.
3. Grok: B15 (light rules), then B7 reviews of Codex's branches, B1 second look, STATUS note.
4. Gemini calendar B10/B11 is parked until Phil asks; agy is out through Oct 18.
5. Check usage before and after each item; keep branches separate and test with fakes.
## Done
- **B2 Lessons + summaries (Tally-11, 2026-10-11):** after a room session of 3+ turns (not on Ctrl+C), the cheapest eligible bot gets one short call and writes 3-5 one-line lessons into the primary project's memory (new memory kind `lesson`, also in `megazword export`). The next session's state card shows the latest 3. That call is logged with `lessons: true`. Summary files were already in B1. `room post-summary` now only prints unless you add `--post`, and tests block `gh`, after a test run posted about 12 fake summaries to Q (Ledger's report). 578 passed, smoke 36/36.
- **B1 Room engine (Atlas-11 / Antigravity, 2026-10-11):** Built `src/megazword/room.py` and CLI commands `megazword room start|stop|say|show|post-summary`. Hive room JSONL storage (`~/.megazword/rooms/<room>.jsonl`), turn loop with `@mentions` targeting, Phil-first priority rule, prime directive prompt, turn cap (default 12), out/over-pace early stops, lean read-only one-shots, and ~80-word replies. Implements token-budget optimizations: state card (<300 words), rolling summary + last 4 messages with automatic condensation after every 6 turns, waking only the needed AI (burn order fallback), CLI session reuse where supported, and per-turn prompt size logging to `log.jsonl`. 541 passed, smoke 31/31. Branch `agy/b1-room`, handed to Tally-11 to merge.
- **Gemini usage meter (Tally-11, 2026-10-11):** `usage_sources.gemini()` runs `agy -p /usage --output-format json` (Antigravity's quota panel, documented; field shape command.data.groups[].buckets[] with remaining_fraction + reset_time, from a public bug report, not yet seen on Phil's PC). Gemini-group buckets become the 5-hour/weekly meter; other groups shown, never block. No agy: falls back to run counts. Tests never run a real agy (conftest). Verified end to end in the cloud with a fake agy and fake Codex log: `megazword usage`, start screen and dashboard /api/state all show codex 42% and gemini 30%. **Not verified live:** real agy JSON on Phil's PC, and the Claude meter (needs his login). Check: `megazword usage`. If gemini shows an error, paste `agy -p /usage --output-format json` output to fix the parser. 520 passed / 1 skipped, smoke 27/27.
- **Gemini via Antigravity (Tally-11, Claude cloud, 2026-10-11, Phil's request):** Google retired the Gemini CLI for personal accounts; `-m gemini` now runs `agy -p --mode plan --output-format text --disable-slash-commands` (prompt on stdin) when `agy` is on PATH, else the old `gemini` command. Doctor finds agy; login hint says `agy`. Flags from Phil's `agy --help` (1.3.3). Phil installed and signed in to agy on his PC. **Not yet verified live:** that agy print mode reads the prompt from stdin. Check on the PC: `megazword run -m gemini "say hi"`. If agy ignores stdin, switch AGY_ARGS in backends.py to pass `{prompt_file}` or `{prompt}`. 517 passed / 1 skipped, smoke 27/27.
- **Beta 1 (2026-10-11, Tally-11, Claude cloud, Phil's call):** merged `codex/guide` (C7 user guide + SPEC status, Cedar-7 Tailscale note), version 0.1.0b1, marker branch `release/beta-1` (tag push blocked from the cloud; Next up item 5). 515 passed / 1 skipped, smoke 27/27. Anything still only on a PC was not in the remote; push it and it goes into beta 2.
- Cedar-7 (Codex, 2026-10-11): clarified that remote dashboard use requires both Tailscale access and the per-launch token in `docs/GUIDE.md`; documentation-only.
- Lean one-shots (Forge, F22, 2026-10-11): routed `claude -p` now adds --strict-mcp-config --disable-slash-commands --restricted (all documented; permission modes untouched; `[oneshot] lean = false` turns it off). Measured direct, "Reply with exactly: pong", 2 runs each: normal 6.6s/6.9s, ~32-33k context tokens, API-equivalent $0.14/$0.12; lean 3.5s/3.6s, ~10.7k tokens, $0.021/$0.002; answers identical. Edit mode verified still writes files. Rejected: --bare (skips OAuth, breaks subscription login); codex --ignore-user-config (drops Phil's model choice) and --ephemeral (kills the Codex usage meter). Codex `-c mcp_servers={}` measured 2026-10-11 ~03:00 (2 runs each): 5.5s/6.0s -> 4.7s/4.8s, tokens identical (6,315), same answer; shipped under [oneshot] lean. Grok has no documented startup-trim flag.
- Reed-09 (Codex) bug-fix review merged by Forge (F12, 2026-10-11). Landed: dashboard jobs publish "done" only after both output readers finish (no lost final output); job start/state snapshots share a lock and retention evicts only finished jobs (all slots running -> clear error); API rejects non-object JSON, list-valued model, negative Content-Length (400) and bodies over 1 MB (413), launch/file errors return JSON 500; explicit X-MZ-Token beats a stale cookie, malformed cookies -> 403; answers.recent() reads under the file lock, skips non-object records, keep<1 rejected; run table escapes prompt/answer counts and tolerates string seconds; doctor reports wrong config types as FAIL and continues. Already covered on main and dropped from the review: cancel process tree (filelock/_kill_tree), answers writer lock (filelock + write_atomic), 24h chart full-day count (runs_24h).
- Reed-09 (Codex, C7): `docs/GUIDE.md` covers all commands in `megazword --help`, daily use, dashboard panels, Tailscale browser access, and doctor-led troubleshooting. `docs/SPEC.md` now marks each build step built or partly built with its command. Branch `codex/guide`, ready for Kestrel to merge.
- Repo created with handoff rules (AGENTS.md), spec, status and decision log.
- Repo made public; AGPL-3.0 license and README added.
- Step 1 part 1: package + `megazword run -m <ai>` + `megazword backends`. Backends for claude, codex, grok all answer a real prompt (tested 2026-10-10). 6 tests pass with fake backends.
- Step 1 part 2: `megazword run "..."` with no `-m` rates difficulty with local qwen2.5:1.5b via Ollama (keyword rule can raise to hard; falls back to the rule if Ollama is down), picks the first installed AI from the route table, prints why, and logs each run to `~/.megazword/log.jsonl`. Overrides in `~/.megazword/config.toml`. 13 tests pass.
- Step 2 part 1: `megazword usage` shows live plan meters. Claude: Anthropic usage endpoint with the saved Claude Code login (Phil approved 2026-10-10; token never printed). Codex: rate_limits snapshot from ~/.codex/sessions logs. Grok: no local meter exists, shows 'not tracked yet'. Code in `src/megazword/usage_sources.py`.
- Step 2 pacing (Codex wrote `pacing.py`, Claude reviewed/merged): auto-pick now skips AIs that are out (>=95%) or over pace (hard tasks only) and otherwise keeps the route order (cheapest first). Exception (Phil, 2026-10-10): a plan within 1h (5-hour window) or 24h (weekly) of reset with >=20% unused is used first, so leftover usage isn't wasted. Unrecognized windows never block (Phil: Claude's "iguana_necktie" is likely his Claude Cloud credit).
- Step 4 shared memory (Claude): `megazword note`, `decide`, `history`; `run --context` prepends decisions + recent activity; every run logs a 'done' entry. Stored in ~/.megazword/projects/<project>/memory.jsonl. 26 tests pass.
- Step 3 escalate-on-failure (Grok wrote `escalate.py` + `OllamaBackend`; Claude merged and wired it in): `megazword run` without `-m` tries the ranked route for the task's difficulty, then stronger routes; a crash, empty answer or refusal moves to the next AI with the earlier attempt as context. `-m` never escalates. Every attempt is logged and recorded in project memory. OllamaBackend exists but isn't registered or routed yet (Phil hasn't said local models should answer tasks). 87 tests pass.
- Overnight 2026-10-11:
  - `megazword import-hive <workshop clone>` (Claude): copies old Hive DECISIONS.md bullets (with original dates) and non-done handoffs into project memory 'hive'. Re-running adds nothing new. Ran it live: 28 decisions + 3 open handoffs imported from a snapshot of workshop origin/main.
  - Project-memory context is capped (newest 15 decisions, 300 chars each) so `--context` stays cheap.
  - `megazword retry` (Claude): rejects the last answer and asks the strongest untried AI (hard route first), passing the rejected answer as context. Last run saved in ~/.megazword/last_run.json.
  - Every routed prompt starts with a one-line note telling the AI to skip session startup / coordination routines (Grok one-shot went from 28s to 4s).
  - Codex: `runlog.py` (per-AI run summaries), Grok usage from Mega Zword's own log, `megazword usage` shows a 24h runs table, `megazword init` writes a commented config with only installed AIs, README rewritten for the public. Claude fixed a double count (rejections were also counted as failures).
  - `tests/conftest.py` isolates every test from the real ~/.megazword. 98 tests pass.
  - `megazword chat` (Codex): interactive session, last 3 turns as context, /retry /model /auto /usage /note /decide /history /context /clear, multi-line input. Forge fixed: rates only the new message; respects [out].
  - `[out]` config (Kestrel): mark an AI out of usage until a date; auto-pick and retry skip it. Grok marked out until 2026-10-17.
  - Grok model/effort per rating (Grok): easy grok-4.6 low, medium grok-4.6 medium, hard grok-4.7 high; `[grok.<level>]` overrides. Forge merged it with edit mode.
  - `run --edit` (Forge): Claude/Grok `--permission-mode acceptEdits`, Codex `-s workspace-write`. Live check: Claude created the file; Codex and Grok answered but didn't create it (under investigation).
  - `megazword dashboard` (Kestrel): local web page at http://127.0.0.1:8765 with plan meters (bar = used, tick = time elapsed), out marks, route table, 24h runs chart, recent runs, project memory + add note/decision, and a run box (auto or pick an AI, include memory, "Not good enough" = retry). Listens on 127.0.0.1 only; POSTs need a per-launch token and a local Host header. Runs go through the normal CLI in a child process, so routing/logging are identical.
  - K1 (Kestrel): Grok gets prompts via `--prompt-file` (Windows caps argv ~32k); Claude/Codex already used stdin. 50k-char test.
  - F1 (Forge): `--edit` on Windows leaves Grok out (its path rules didn't contain writes; its sandbox is Linux/macOS only).
  - K2 (Kestrel): last 50 answers saved to ~/.megazword/answers.jsonl; dashboard "Past answers"; phone-width fix.
  - F2 (Forge): optional answer-quality check (`quality_check = true`), local model flags dodges, which then escalate. Off by default.
  - K3 (Kestrel): dashboard shows elapsed time and a Cancel button for running jobs. (True token streaming isn't possible: the CLIs print the answer at the end.)
  - U3 (Kestrel): `megazword dashboard --host <tailscale-ip>` for phone access. Every request needs the per-launch token (link printed in the terminal), and it refuses 0.0.0.0.
  - C1/C2 (Codex reed09): `megazword doctor` (read-only setup check, all OK live) and `scripts/install.ps1` (user PATH only; NOT run yet, Phil should run it).
  - F3 (Forge): `scripts/smoke.py`: end-to-end with fake CLIs, no network or paid calls. Run after every merge.
  - C3/U1 (Codex Astra): public README; rough est_tokens per run in usage + dashboard; 24h chart counts the whole window.
  - U2 (Forge): `megazword out [<ai> --until 7d|date|--clear]` + dashboard buttons. Also fixed tests touching the real ~/.megazword.
  - F4 (Forge): per-AI `[timeouts]`; a hung AI's whole process tree is killed.
  - C4 (Codex): OpenRouter + Groq backends (key from env; never routed by default).
  - F5 (Forge): log/memory line caps (`[limits]`), decisions never trimmed; dashboard Cancel kills the AI's process tree.
  - F6 (Forge): `megazword stats` + 7-day trend chart on the dashboard.
  - C5 (Codex): Gemini CLI backend (read-only plan mode, never in edit mode, not routed by default; Gemini isn't installed here).
  - F7 (Forge): chat Ctrl+C cancels the call, not the chat; `/cost`; persistent history if pyreadline3 is installed.
  - C6 (Codex, finished by Kestrel review): dashboard Settings panel: route order, timeouts, limits, quality_check; safe config writer (atomic, validates, restores on failure).
  - F8 (Forge): cross-process file locks for log/memory/answers/last_run (fixed real torn lines from parallel dashboard jobs).
  - F9 (Forge): compare mode: `run --compare claude,codex "..."` + dashboard Compare (side by side, stacks on phones).
  - F10 (Forge): usage-limit errors auto-mark that AI out until its reset (tested on Codex's real message); config writes locked.
  - F11 (Forge): "this one's best" votes on compare, `megazword advise` (suggests route order, never applies), Suggestions box on the dashboard.
  - Dashboard visually checked (headless Edge screenshot) with real data; phone grid fix.
  - F13 (Forge): 20x full-suite loop, 0 failures in 6,460 test runs; timing-based asserts made deterministic.
  - F14 (Forge): `scripts/live_check.py --yes-spend`: Phil's opt-in real check (one "pong" per AI + one auto run).
  - F15 (Forge): `megazword dashboard --app` (own Edge window); `scripts/install.ps1 -Shortcut` (Desktop + Start Menu); MZ favicon.
  - F16 (Forge): `megazword projects` + dashboard project switcher (traversal-safe names).
  - F17 (Forge): GitHub Actions CI (.github/workflows/test.yml): pytest + smoke on Windows and Ubuntu, Python 3.11 and 3.12, every push and PR, no secrets. First run 38166747316 passed. Warnings to handle later: checkout/setup-python run on deprecated Node 20; ubuntu-latest becomes Ubuntu 26 on Oct 19.
  - F19 (Forge): dashboard notifications when a job finishes in a hidden tab, "/" and Esc shortcuts, copy buttons.
  - F20 (Forge): plain-English failure reasons with the fix (login, network, missing, timeout, limit); two network failures in a row stop the chain; only limits mark an AI out.
  - F21 (Forge reviewing Codex's code): config typo or BOM no longer crashes every command; free-API network/429 messages fixed; doctor can't hang on .cmd shims; install.ps1 no longer flattens %VARS% in the user PATH (would have damaged Phil's PATH).
  - F22 (Forge): lean Claude one-shots (--strict-mcp-config --disable-slash-commands --restricted): ~6.7s -> ~3.5s, ~33k -> ~11k context tokens, same answers; `[oneshot] lean = false` turns it off. Codex lean flag measured after its reset.
  - F23 (Forge): plain `megazword` shows a start screen (plans, out marks, last runs, top commands).
  - F24 (Forge): one meter summary shared by start screen, `usage` and dashboard; snapshot age shown; out AIs show "out until X".
  - Codex lean (Forge): `-c mcp_servers={}` on one-shots: ~5.8s -> ~4.75s, same tokens and answers.
  - C8 (Codex): grouped `--help` with examples; one-line errors instead of tracebacks; start screen fits 80 columns.
  - C9 (Codex): dashboard accessibility (contrast AA, focus rings, labels, live regions, chart text summaries, 44px phone targets).
  - C10 (Codex): `megazword export [-p P] [--since 7d] [--out FILE]` Markdown report.
  - F25 part 1 (Forge): start screen no longer prints "Plans:" twice; export escapes only what Markdown needs; export always writes UTF-8 (a Windows `>` redirect wrote cp1252 and crashed on emoji).
  - 516+ tests, 27/27 smoke checks pass.

## In progress
- **Nimbus-12 (Grok Build):** R1 table is in this file under B14. Next: B3 tabs backend on `grok/beta2-2026-10-11`. Agy stdin and the real agy /usage output are unverified until someone runs Next up item 4 on the PC.

## Overnight backlog (2026-10-11; some items are done, so check Done first)
Rules: take the top unclaimed item in your lane, write your name next to it,
work on a branch, push, hand the branch to Kestrel to merge. Tests must pass.
Never spend paid usage in tests. Don't change routing defaults or turn on
local-model answering without Phil (that's his call; leave a note instead).

Kestrel (lead, main):
- K1 Send prompts on stdin instead of the command line for every CLI that
  supports it (Grok, Claude, Codex); Windows caps argv at ~32k chars, so long
  `--context`/chat prompts can fail. Test with a 50k-char prompt on a fake.
- K2 Dashboard: phone-friendly layout check; save each run's prompt + answer
  (last 50, ~/.megazword/answers.jsonl) so the dashboard can show past answers.
- K3 Dashboard: live streaming of the answer while it's generated.

Forge:
- F1 (claimed) `--edit`: why Codex/Grok answer but don't create files.
- F2 Answer-quality check: after an auto run, a fast local/free check flags
  answers that dodge the question (beyond the current refusal/empty rules);
  flagged answers escalate like failures. Off by default, config switch.
- F3 End-to-end smoke script (`scripts/smoke.ps1`) using fake CLIs on PATH:
  run, retry, chat, dashboard API, usage. No paid calls.

Codex (Phil starts Codex sessions; Kestrel may dispatch via
`megazword run -m codex --edit` in its own worktree):
- C1 (claimed) `megazword doctor` + `scripts/install.ps1`.
- C2 Make `megazword` runnable from any folder (pipx/PATH) and document it.
- C3 README: dashboard section, chat section, config reference for [out],
  [route], [grok.<level>].

- F24 (Forge, next): meter consistency. Start screen says "codex no meter" while `usage` shows a Codex snapshot and the dashboard shows it out. One shared summary for all three; show snapshot age ("as of 12:13 AM", stale after 1h); out-marked AIs show "out until X" instead of a bar.

- Nit: export escapes the hyphen in the title ("mega\-zword"); only escape where Markdown needs it.

- F25 leftovers (dashboard, found by Forge, not fixed yet):
  (a) #jobs has aria-live and is re-rendered every 0.8s, so screen readers re-announce constantly. Drop it; announce only on job finish via an sr-only status region.
  (b) renderJob keeps focus only on Cancel; focus on copy/vote/answer is lost every poll.
  (c) load() rebuilds the #model select every 30s even while it's focused or open; skip when it's document.activeElement.
- Flaky: one dashboard test failed once with a connection error, passed on rerun.

Unassigned / ideas:
- U4 Codex's meter showed low usage but Codex (gpt-6-astra) hit its limit at ~00:07. Read the limit error ("try again at <time>") from a failed run and auto-mark the AI out until then.
- U1 Token/usage estimate per run in the log (chars -> rough tokens) and a
  per-AI "cost" column in usage + dashboard.
- U2 `megazword out grok --until 2026-10-17` command (edit config from CLI)
  and an "out" toggle on the dashboard.
- U3 Dashboard `--host` for Tailscale with token required on GET too (step 5
  prep; keep 127.0.0.1 default).

## Next step (needs Phil)
- Morning live check (costs a few dozen tokens per AI): from C:\Users\mrmar\mega-zword run `.venv\Scripts\python scripts\live_check.py --yes-spend`. Runs doctor (stops on FAIL), sends "Reply with exactly: pong" once to each installed, not-out AI via `megazword run -m`, then once via auto-pick, and prints AI / ok / seconds / answer length. Without --yes-spend it only explains itself. Never run by the bots.
Build step 5: phone access (see SPEC.md). Needs Phil at the PC and phone.
1. Install Tailscale on PC and phone, sign in to the same account.
2. Enable Windows OpenSSH Server (admin PowerShell:
   `Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0`,
   `Start-Service sshd`, `Set-Service sshd -StartupType Automatic`).
3. Install Termux on the phone, `pkg install openssh`, `ssh mrmar@<pc-tailscale-ip>`.
4. On the PC: `megazword dashboard --host <PC tailscale IP>`, open the printed link on the phone.
5. Turn off "Expose Ollama to the network" (or firewall 11434 to the Tailscale
   interface only). Optional: phone model server in Termux as an extra backend.

## How to run (dev)
    python -m venv .venv
    .venv/Scripts/python -m pip install -e ".[dev]"
    .venv/Scripts/python -m pytest -q
    .venv/Scripts/megazword backends
    .venv/Scripts/megazword run "your prompt" -m claude   # or codex / grok

## Machine facts (checked 2026-10-10)
- Installed: claude 2.1.296, codex-cli 0.162.1, grok 1.0.50, Python 3.11.9, git, gh.
- Ollama 0.40.2 installed via winget 2026-10-10; model qwen2.5:1.5b pulled (rater). First rater call after idle takes up to ~60s while the model loads; warm calls ~1s. Phil turned on "Expose Ollama to the network"; it listens on all interfaces. Lock down when doing phone access (step 5).
- Not installed: gemini CLI.

## Problems / notes
- The Grok session that wrote step 3 stopped with about 9% of its own Grok 4.7 weekly limit left (the meter in the Grok CLI status bar, not a Mega Zword plan). Do not wait on that session.
