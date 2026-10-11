# Status

**Active:** none
**Last updated:** 2026-10-10 by Claude Code

## Done
- Repo created with handoff rules (AGENTS.md), spec, status and decision log.
- Repo made public; AGPL-3.0 license and README added.
- Step 1 part 1: package + `megazword run -m <ai>` + `megazword backends`. Backends for claude, codex, grok all answer a real prompt (tested 2026-10-10). 6 tests pass with fake backends.
- Step 1 part 2: `megazword run "..."` with no `-m` rates difficulty with local qwen2.5:1.5b via Ollama (keyword rule can raise to hard; falls back to the rule if Ollama is down), picks the first installed AI from the route table, prints why, and logs each run to `~/.megazword/log.jsonl`. Overrides in `~/.megazword/config.toml`. 13 tests pass.

## In progress
- Nothing.

## Next step
Build step 2: usage tracking and reset-aware pacing (see SPEC.md).
1. `megazword usage` command: summarize `~/.megazword/log.jsonl` per AI
   (runs today / this week, failures, total seconds).
2. Find out what each CLI can report about its own plan limits, and record
   the findings in this file before coding against them:
   - Claude Code: `/usage` (interactive) and local logs under `~/.claude/projects`.
   - Codex: `/status` (interactive) and logs under `~/.codex/sessions`.
   - Grok: `grok usage` subcommand exists (prints per-session token/cost usage).
   Prefer whatever is readable non-interactively without spending usage.
3. Add plan windows to config (reset time + window length per AI) and a
   pacing check: % used vs % of window elapsed. Over pace -> AI only takes
   hard tasks. Feed this into `pick()` in cli.py.
4. Tests with fake log data.

Open question for Phil: the default route order in `config.py`
(easy -> grok, medium -> codex, hard -> claude) is a placeholder. Pacing in
step 2 should replace most of it.

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
- None yet.
