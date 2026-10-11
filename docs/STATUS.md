# Status

**Active: none. Kestrel remains in charge of main, merges and assignments (Phil’s call).**
- **Kestrel** (Claude Code): lead. Owns main, decides merges and assignments, also building `megazword dashboard` (claude/dashboard).
- **Forge** (Claude Code): edit-mode fixes on branch claude/edit-mode; hands finished branches to Kestrel.
- **Codex**: C7 user guide and spec status complete on `codex/guide`; see `docs/GUIDE.md`. C1/C2 doctor and installer work is on `codex/doctor`.
**Last updated:** 2026-10-11 by Tally-11 (Claude cloud): Beta 1 tagged

## Done
- **Gemini via Antigravity (Tally-11, Claude cloud, 2026-10-11, Phil's request):** Google retired the Gemini CLI for personal accounts; `-m gemini` now runs `agy -p --mode plan --output-format text --disable-slash-commands` (prompt on stdin) when `agy` is on PATH, else the old `gemini` command. Doctor finds agy; login hint says `agy`. Flags from Phil's `agy --help` (1.3.3). Phil installed and signed in to agy on his PC. **Not yet verified live:** that agy print mode reads the prompt from stdin. Check on the PC: `megazword run -m gemini "say hi"`. If agy ignores stdin, switch AGY_ARGS in backends.py to pass `{prompt_file}` or `{prompt}`. 517 passed / 1 skipped, smoke 27/27.
- **Beta 1 (2026-10-11, Tally-11, Claude cloud, Phil's call):** merged `codex/guide` (C7 user guide + SPEC status, Cedar-7 Tailscale note), version 0.1.0b1, tag `v0.1.0-beta.1`. 515 passed / 1 skipped, smoke 27/27. Anything still only on a PC was not in the remote; push it and it goes into beta 2.
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
- Kestrel: dispatch/merge. Forge: F22. Reed-09's C7 documentation is complete on `codex/guide` and queued for Kestrel to review and merge.

## Overnight backlog (2026-10-11, Phil asleep; Kestrel assigns)
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
