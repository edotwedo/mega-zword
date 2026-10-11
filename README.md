# Mega Zword

Mega Zword is a Python command line tool that routes prompts to installed AI command line tools such as Claude Code, Codex, and Grok. It rates task difficulty, tracks its own runs, checks available plan usage, and tries another AI when one fails.

**Status:** Early development, pre-1.0. Tested on Windows.

## Requirements

- Python 3.11 or newer.
- At least one of the Claude Code, Codex, or Grok command line tools, installed and logged in.
- Ollama is optional. It rates difficulty locally; without it, Mega Zword uses a simple rule.

## Install

```powershell
git clone https://github.com/edotwedo/mega-zword.git
cd mega-zword
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
```

## Quick start

```text
megazword init
megazword backends
megazword usage
megazword run "Summarize this folder"
megazword run -m claude "Explain this function"
megazword note "The API uses JSON"
megazword decide "Keep the public API stable"
megazword history
megazword run --context "Fix the bug"
```

`init` creates a default config using the AI tools it finds. `-m` selects an AI directly. `--context` adds project decisions and recent activity to the prompt.

## Routing

Mega Zword rates a prompt as easy, medium, or hard, then follows that level's ordered route in the config. It checks plan usage when a meter is available: plans at 95% or more are skipped, and plans being used faster than time passes are reserved for hard tasks. Near a reset, leftover usage may be spent. If an AI refuses, returns no answer, or fails, Mega Zword tries the next AI in the route.

## Files

Configuration, run logs, and project notes live in `~/.megazword` (on Windows, `%USERPROFILE%\.megazword`). The config file is `config.toml`; run counts are in `log.jsonl`.

## License

GNU Affero General Public License v3.0 (AGPL-3.0). See [LICENSE](LICENSE). Versions before 1.0 stay AGPL-3.0.
