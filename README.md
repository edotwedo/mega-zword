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
.\scripts\install.ps1
```

On Windows, the installer uses `pipx` when available. Otherwise it creates or
refreshes `.venv` and adds its `Scripts` folder to your user PATH. It is safe to
run again after updating the checkout. Open a new terminal to use `megazword`
from any folder. The installer finishes with `megazword doctor`.

To install manually instead: `python -m venv .venv`, then
`.venv\Scripts\python -m pip install -e .`.

## Quick start

```text
megazword init
megazword backends
megazword usage
megazword doctor
megazword run "Summarize this folder"
megazword run -m claude "Explain this function"
megazword retry
megazword note "The API uses JSON"
megazword decide "Keep the public API stable"
megazword history
megazword run --context "Fix the bug"
```

`init` creates a default config using the AI tools it finds. It keeps an existing config unless you pass `--force`. `-m` selects an AI directly. `--context` adds project decisions and recent activity to the prompt.

## Dashboard

```text
megazword dashboard
megazword dashboard --port 8766 --no-browser --project my-app
```

The default opens `http://127.0.0.1:8765` on this computer. The page shows plan meters, routes, 24-hour run counts, recent runs, past answers, and project memory. You can send a prompt, pick an AI, include memory, or click **Not good enough** to retry. Running jobs show elapsed time and a Cancel button. Answers appear when the AI finishes.

For phone access, connect the PC and phone to the same Tailscale network. Find the PC's address with `tailscale ip -4`. Pass that address as `--host`:

```text
megazword dashboard --host 100.101.102.103 --project my-app
```

Replace the example IP with your PC's Tailscale IP. Open the full link printed in the terminal on your phone. It looks like `http://100.101.102.103:8765/?t=<token>`. The token is required for remote access and changes each launch. Anyone with the link can run your AIs; keep it private. Remote mode does not open a browser automatically. Listening on `0.0.0.0` or `::` is refused. Press Ctrl+C in the terminal to stop the server.

## Chat

```text
megazword chat
```

Type a message at `mz>`. Each answer uses the normal router. Chat includes up to three recent turns, with long turns clipped. Project memory starts off. Use `/context on` to include it.

| Command | What it does |
|---|---|
| `/help` | Show commands. |
| `/quit` | End chat. Ctrl+C or end of input also exits. |
| `/model claude` | Pin the AI for new messages. `/model` lists names. |
| `/auto` | Return to automatic AI selection. |
| `/retry` | Retry the last saved answer through the retry route. |
| `/usage` | Show plan meters and 24-hour run totals. |
| `/note The API uses JSON` | Save a project note. |
| `/decide Keep the API stable` | Save a project decision. |
| `/history` | Show the last 20 memory entries. |
| `/context on` or `/context off` | Include or omit project memory. |
| `/clear` | Clear the chat's conversation context. Saved memory stays. |

For multiple lines, end a line with `\`, or paste a block between `<<<` and `>>>` on their own lines:

```text
mz> <<<
... Explain this function.
... Suggest two simpler names.
... >>>
```

Chat uses the current repo or folder for its project name. `/retry` uses the last saved run, including a run from outside this chat; it does not use the pinned model.

## Let an AI edit files

Run from the folder you want to change:

```text
megazword run --edit "Fix the failing test"
megazword run --edit --model codex --context "Add input validation"
```

`--edit` (short form `-e`) enables the backend's file-edit permissions. Claude uses `acceptEdits`; Codex uses `workspace-write`. Review the changes afterward. On Windows, Grok is left out of edit-mode routing because its sandbox is not available there. Forcing `--edit -m grok` on Windows returns an error.

## Retry an answer

```text
megazword run "Explain the failing test"
megazword retry
megazword retry --model claude
```

`retry` passes the last saved prompt and rejected answer to another AI. It skips the last answerer and tries the hard route first, then the saved route. It skips unavailable AIs and AIs marked out. `-m` (or `--model`) requests a particular alternative. If none is left, it reports that. The saved run is shared across projects. Retry has no `--edit` flag and does not preserve edit permissions.

## Notes, decisions, and history

```text
megazword note "The API uses JSON" --project my-app --by alex
megazword decide "Keep the public API stable" -p my-app
megazword history -p my-app -n 10
megazword run --context -p my-app "Suggest the next change"
```

`note` saves information. `decide` saves a project decision. Both accept `--by`; its default is `phil`. `history` shows the last 20 entries unless you set `-n`. These commands use the current repo or folder when `--project` (short form `-p`) is omitted. Notes and decisions reach an AI when you include project memory with `--context` (short form `-c`), `/context on`, or the dashboard checkbox. Each run attempt also adds a memory entry.

`doctor` checks Python, the CLI tools and their versions, Ollama and the rater
model, config routes and active `[out]` marks, usage meters, and log access. It
prints OK, WARN, or FAIL for each check. WARN covers optional or unavailable
components; FAIL means the local installation needs repair. It exits with code
1 if any check fails, otherwise 0. It never sends an AI prompt.

## Routing

Mega Zword rates a prompt as easy, medium, or hard, then follows that level's ordered route in the config. It checks plan usage when a meter is available: plans at 95% or more are skipped, and plans being used faster than time passes are reserved for hard tasks. Near a reset, leftover usage may be spent. If an AI refuses, returns no answer, or fails, Mega Zword tries the next AI in the route.

## Usage meters

- **Claude:** `megazword usage` asks Anthropic's usage endpoint using the login Claude Code already saved on your computer. The token is sent only to api.anthropic.com and is never printed or logged. This endpoint is unofficial and may change.
- **Codex:** read from the rate-limit snapshot Codex writes to its own session logs, so it is as fresh as your last Codex run.
- **Grok:** no meter is available, so Mega Zword reports how many runs it sent to Grok.

The 24-hour runs table also shows `est_tokens` per AI. Each attempt logs `(prompt_chars + answer_chars) // 4`. This is a rough size estimate, not billed tokens, money, or remaining quota. It counts the original prompt and returned answer; added memory, chat context, tool calls, and internal reasoning are not measured. Old log entries without an estimate count as zero. Failed and rejected attempts are included. The dashboard shows the same daily total in each chart tooltip and a per-attempt estimate in Recent runs.

## Config reference

Edit `~/.megazword/config.toml`. Run `megazword init` to create a starting file with only installed AIs in its routes. Omitted settings use defaults. Restart a running chat or dashboard after changing the file.

This example shows the routing and model defaults, plus an optional out mark:

```toml
# Top-level settings must come before the tables below.
rater_model = "qwen2.5:1.5b"
quality_check = false

[route]
easy = ["grok", "codex", "claude"]
medium = ["codex", "claude", "grok"]
hard = ["claude", "codex", "grok"]

[out]
# Example only: replace with your reset date, or remove this line.
grok = 2026-10-17T23:30:00-07:00

[grok.easy]
model = "grok-4.6"
effort = "low"

[grok.medium]
model = "grok-4.6"
effort = "medium"

[grok.hard]
model = "grok-4.7"
effort = "high"
```

| Setting | Meaning |
|---|---|
| `rater_model` | Ollama model used to rate difficulty. Defaults to `qwen2.5:1.5b`. If rating is unavailable, a keyword rule is used. This does not add Ollama to the answering route. |
| `quality_check` | Defaults to `false`. Set to `true` for a local answer check on automatically selected runs. Flagged answers can escalate. It uses `rater_model`; forced `-m` runs bypass the check. |
| `[route]` | Ordered AI names for `easy`, `medium`, and `hard`. Routing considers installation, pacing, and out marks. Failures can move into harder routes. |
| `[out]` | AI name mapped to a return date or time. Auto selection and retry skip it until then. A bare date such as `2026-10-17` means the start of that day in local time. A time without an offset also uses local time. Remove the entry to clear the mark early. A forced `run -m` bypasses out marks. |
| `[grok.<level>]` | Grok `model` and `effort` for each difficulty. Missing fields keep their defaults. A forced `run -m grok` uses `medium`; retry promotes `easy` to `medium`. |

## Files

Configuration, run logs, and project notes live in `~/.megazword` (on Windows, `%USERPROFILE%\.megazword`). Set `MEGAZWORD_HOME` to use another folder. The config file is `config.toml`; attempts are in `log.jsonl`. Project memory lives under `projects/`. `last_run.json` supports retry. `answers.jsonl` keeps the last 50 prompt-and-answer pairs.

## License

GNU Affero General Public License v3.0 (AGPL-3.0). See [LICENSE](LICENSE). Versions before 1.0 stay AGPL-3.0.
