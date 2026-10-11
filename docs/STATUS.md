# Status

**Active:** none
**Last updated:** 2026-10-10 by Claude Code

## Done
- Repo created with handoff rules (AGENTS.md), spec, status and decision log.
- Repo made public; AGPL-3.0 license and README added.

## In progress
- Nothing.

## Next step
Build order step 1 (see SPEC.md). Concretely:
1. Create `pyproject.toml` for package `megazword` (Python 3.11) with a
   `megazword` console command.
2. Write a backend interface plus one backend per installed CLI
   (`claude -p`, `codex exec`, `grok -p`), each just runs a prompt and returns
   the text.
3. `megazword run "<prompt>" --model <name>` runs a prompt on a chosen backend.
4. Add a test that runs with a fake backend (no paid usage).

## Machine facts (checked 2026-10-10)
- Installed: claude 2.1.296, codex-cli 0.162.1, grok 1.0.50, Python 3.11.9, git, gh.
- Not installed: gemini CLI, ollama.

## Problems / notes
- None yet.
