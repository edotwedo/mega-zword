# Status

**Active (2026-10-11 ~00:20). Kestrel is in charge (Phil's call):**
- **Reed-09** (Codex, 2026-10-11): Kestrel-assigned dashboard/answers/doctor/installer bug review in isolated `codex/review` worktree; fixes and regression tests in progress.
- **Kestrel** (Claude Code): lead. Owns main, decides merges and assignments, also building `megazword dashboard` (claude/dashboard).
- **Forge** (Claude Code): edit-mode fixes on branch claude/edit-mode; hands finished branches to Kestrel.
- **Codex**: `megazword doctor` + scripts/install.ps1 on branch codex/doctor (brief from Forge via Phil).
**Last updated:** 2026-10-10 by Claude Code

## Done
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
  - 142 tests pass.

## In progress
- Kestrel: K3. Forge: F3 then U2. Codex/Astra (headless): C1+C2 on codex/doctor. Kestrel heartbeat runs at :13/:43.

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

Unassigned / ideas:
- U1 Token/usage estimate per run in the log (chars -> rough tokens) and a
  per-AI "cost" column in usage + dashboard.
- U2 `megazword out grok --until 2026-10-17` command (edit config from CLI)
  and an "out" toggle on the dashboard.
- U3 Dashboard `--host` for Tailscale with token required on GET too (step 5
  prep; keep 127.0.0.1 default).

## Next step (needs Phil)
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
