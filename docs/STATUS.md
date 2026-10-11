# Status

**Active:** Claude Code, since 2026-10-10 22:15 (building step 1)
**Last updated:** 2026-10-10 by Claude Code

## Done
- Repo created with handoff rules (AGENTS.md), spec, status and decision log.
- Repo made public; AGPL-3.0 license and README added.
- Step 1 part 1: package + `megazword run -m <ai>` + `megazword backends`. Backends for claude, codex, grok all answer a real prompt (tested 2026-10-10). 6 tests pass with fake backends.

## In progress
- Build step 1, part 2: difficulty rating + automatic pick + usage log.

## Next step
1. Pull a small local model for rating difficulty (`ollama pull qwen2.5:1.5b`).
2. `src/megazword/rater.py`: send the prompt to Ollama's HTTP API
   (http://127.0.0.1:11434/api/generate, stdlib urllib, no new deps) and get
   back easy / medium / hard plus a one-line reason. If Ollama is down, fall
   back to a simple length/keyword rule and say so.
3. `megazword run "<prompt>"` without `-m` rates the prompt, picks a backend
   (easy -> cheapest, hard -> strongest; table in a config file), prints the
   choice and reason, then runs it. `-m` still overrides.
4. Append one line per run to `~/.megazword/log.jsonl` (time, backend,
   rating, seconds, ok). This is the start of usage tracking.
5. Tests with fake backends and a fake rater.

## How to run (dev)
    python -m venv .venv
    .venv/Scripts/python -m pip install -e ".[dev]"
    .venv/Scripts/python -m pytest -q
    .venv/Scripts/megazword backends
    .venv/Scripts/megazword run "your prompt" -m claude   # or codex / grok

## Machine facts (checked 2026-10-10)
- Installed: claude 2.1.296, codex-cli 0.162.1, grok 1.0.50, Python 3.11.9, git, gh.
- Ollama 0.40.2 installed via winget 2026-10-10 (no models pulled yet).
- Not installed: gemini CLI.

## Problems / notes
- None yet.
