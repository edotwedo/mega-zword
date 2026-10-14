# Hive floor

Phil, 2026-10-12: unfreeze. One seat for every model we can run. Launch **one**
Claude, **one** Codex, **one** Grok. They spawn subagents. Gemini CLI (`agy`) gets a chair when its week is back (18 Oct). HTTP seats
(Groq, Cloudflare, Z.ai, Gemini API, Mistral, Cerebras, SambaNova) get their
own persistent `megazword chat -m <name>` window on a separate Windows
desktop (`scripts/free_floor.ps1`). OpenRouter stays off (pay-per-use).
NVIDIA sits empty until the key arrives.

## Ready

`megazword floor` prints the roster and writes `~/.megazword/floor.json`.
Ready means claude, codex and grok are seated or honestly marked out. Empty
CLI chairs mean the floor is not ready.

`megazword floor introduce` posts that roster into the Hive room (no @mentions,
so Start does not wake everyone). `peek` and `wait` read the same log every
seat posts to.

## Hive MCP

`megazword mcp` is a stdio MCP server on that log, so Claude, Codex and Grok
read and post from inside their own chat without a second pane. Tools:
`hive_read`, `hive_say`, `hive_wait`. Register it in each CLI's MCP config
(command `megazword`, args `["mcp"]`) and set `MEGAZWORD_SEAT` to the seat's
name; `hive_say` posts as that seat.

`scripts/hive_up.ps1` opens the Mega Zword window and one Windows Terminal tab
per main CLI. Each tab gets `MEGAZWORD_SEAT` so Hive MCP posts as that seat.
Skip a name you already have (`-Skip grok` when Grok is this chat).
`megazword floor` prints **Heard in Hive MCP** for seats that called `hive_say`
or connected the server. That is who is actually in the live room. Installed
CLIs can still show as seated while Heard is empty.

## How work happens

Phil enters the Mega Zword **Hive** tab and says what to decide and what to do.
Nobody auto-fires an easy/medium/hard list. Bulk and stand-in work goes to Groq
and the other HTTP seats so Claude/Codex/Grok last for the big projects.

`megazword floor suggest <kind>` names the seated model for a job. It skips
empty and out seats, prints `(no seat)` (exit 1) if nobody fits, and sends
nothing. With every seat filled:

| Kind | Example | Order |
| --- | --- | --- |
| bulk | `megazword floor suggest bulk` → `groq` | groq, mistral, cloudflare, zai, gemini-api, then other HTTP seats (never a CLI) |
| edit | `megazword floor suggest edit` → `codex` | codex, claude |
| decide | `megazword floor suggest decide` → `claude` | claude, grok, codex |
| review | `megazword floor suggest review` → `claude` | claude, grok, codex |

Money and new keys: Phil. The app hunts empty chairs and says what is missing.

## Launched CLI prompt

You are one seat. Check `megazword usage` before you work. During a long job
run `megazword usage --pace` and wrap up at 20% left, stop at 15%. Do not
greet in Q. Wait for Phil in the Hive. Use a subagent for extra hands, not a
second window. HTTP seats stay pinned with `megazword chat -m <name>`.
