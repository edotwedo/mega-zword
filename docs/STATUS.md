# Status

**Active:** none
**Last updated:** 2026-10-10 by Claude Code

## Done
- Repo created with handoff rules (AGENTS.md), spec, status and decision log.
- Repo made public; AGPL-3.0 license and README added.
- Step 1 part 1: package + `megazword run -m <ai>` + `megazword backends`. Backends for claude, codex, grok all answer a real prompt (tested 2026-10-10). 6 tests pass with fake backends.
- Step 1 part 2: `megazword run "..."` with no `-m` rates difficulty with local qwen2.5:1.5b via Ollama (keyword rule can raise to hard; falls back to the rule if Ollama is down), picks the first installed AI from the route table, prints why, and logs each run to `~/.megazword/log.jsonl`. Overrides in `~/.megazword/config.toml`. 13 tests pass.
- Step 2 part 1: `megazword usage` shows live plan meters. Claude: Anthropic usage endpoint with the saved Claude Code login (Phil approved 2026-10-10; token never printed). Codex: rate_limits snapshot from ~/.codex/sessions logs. Grok: no local meter exists, shows 'not tracked yet'. Code in `src/megazword/usage_sources.py`.

## In progress
- Nothing.

## Next step
Build step 2: usage tracking and reset-aware pacing (see SPEC.md).
1. DONE: `megazword usage` (live meters for Claude and Codex).
2. Grok: no plan meter anywhere locally (checked ~/.grok; `grok usage` is
   per-session tokens only). Track Grok ourselves from ~/.megazword/log.jsonl
   and per-session token counts; ask Phil which Grok plan he has.
   Claude's endpoint also returns unexplained windows ("iguana_necktie",
   "extra_usage"); find out what they mean before pacing on them.
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
