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
megazword retry
megazword note "The API uses JSON"
megazword decide "Keep the public API stable"
megazword history
megazword run --context "Fix the bug"
```

`init` creates a default config using the AI tools it finds. `-m` selects an AI directly. `retry` rejects the last answer and asks a stronger AI, showing it the rejected answer. `--context` adds project decisions and recent activity to the prompt.

## Routing

Mega Zword rates a prompt as easy, medium, or hard, then follows that level's ordered route in the config. It checks plan usage when a meter is available: plans at 95% or more are skipped, and plans being used faster than time passes are reserved for hard tasks. Near a reset, leftover usage may be spent. If an AI refuses, returns no answer, or fails, Mega Zword tries the next AI in the route.

## Usage meters

- **Claude:** `megazword usage` asks Anthropic's usage endpoint using the login Claude Code already saved on your computer. The token is sent only to api.anthropic.com and is never printed or logged. This endpoint is unofficial and may change.
- **Codex:** read from the rate-limit snapshot Codex writes to its own session logs, so it is as fresh as your last Codex run.
- **Grok:** no meter is available, so Mega Zword reports how many runs it sent to Grok.

## Files

Configuration, run logs, and project notes live in `~/.megazword` (on Windows, `%USERPROFILE%\.megazword`). The config file is `config.toml`; run counts are in `log.jsonl`.

## License

GNU Affero General Public License v3.0 (AGPL-3.0). See [LICENSE](LICENSE). Versions before 1.0 stay AGPL-3.0.
