# Status

**Active:** none
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

## In progress
- Nothing.

## Next step
Build step 5: phone access (see SPEC.md). Needs Phil at the PC and phone.
1. Install Tailscale on PC and phone, sign in to the same account.
2. Enable Windows OpenSSH Server (admin PowerShell:
   `Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0`,
   `Start-Service sshd`, `Set-Service sshd -StartupType Automatic`).
3. Install Termux on the phone, `pkg install openssh`, `ssh mrmar@<pc-tailscale-ip>`.
4. Make `megazword` runnable from any folder (pipx or add .venv\Scripts to PATH).
5. Turn off "Expose Ollama to the network" (or firewall 11434 to the Tailscale
   interface only). Optional: phone model server in Termux as an extra backend.

Also open (no Phil needed): Grok usage self-tracking from ~/.megazword/log.jsonl;
a `megazword retry` command using escalate(start_after=..., prior_answer=...)
only if Phil asks for it.

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
