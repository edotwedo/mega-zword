# Using Mega Zword day to day

Mega Zword is a local command line tool. It routes a prompt to one of your AI
tools, keeps a run log and project memory, and can show the work in a dashboard.
It does not run tasks in the background. Start it when you need it.

## First setup

Install Python 3.11 or newer and at least one supported AI command line tool;
sign in to that tool first. Ollama is optional. It rates tasks locally and can
run the optional answer check, but Mega Zword does not route answers to Ollama.

In PowerShell, install from a checkout:

```powershell
git clone https://github.com/edotwedo/mega-zword.git
cd mega-zword
.\scripts\install.ps1
```

The installer uses pipx when it is available. Otherwise, it creates or updates
the repository's `.venv` and adds its `Scripts` directory to your user PATH.
Open a new terminal afterward. You can run Mega Zword from any folder once the
new PATH is loaded. The installer finishes with `megazword doctor`. Add
`-Shortcut` if you also want user-level Desktop and Start Menu links that open
the dashboard in an app window.

Set up a starting configuration and inspect this PC:

```text
megazword init
megazword backends
megazword doctor
```

`init` makes `~/.megazword/config.toml` (on Windows,
`%USERPROFILE%\.megazword\config.toml`) with routes for installed AI tools. It
keeps an existing file; use `megazword init --force` only when you mean to
replace it. `backends` lists detected tools. `doctor` checks Python, tool
versions, keys for optional providers, config, Ollama and its rating model,
usage meters, timeouts, and whether the run log can be written. It never sends
an AI prompt. Fix `FAIL` results first. `WARN` usually means an optional tool
or meter is unavailable.

## Sentinel (one-time, Phil)

Sentinel logs reboots, logins and network changes, and can watch production
URLs. It uses no AI usage.

1. Collect once: `megazword sentinel status` (then `megazword sentinel log`).
   Reading the Security log needs your account in the **Event Log Readers**
   group (one admin command). System and network logs work without that.
2. Optional phone push: install the **ntfy** app (no account). Then run
   `megazword sentinel install` — it prints a topic name and saves it in
   `~/.megazword/config.toml`. Subscribe to that topic in the app. Run
   `megazword sentinel install --yes` only when you are ready to create the
   5-minute Windows scheduled task (Phil's call).
3. Optional "PC went offline" alert: create a free check at healthchecks.io,
   then set `[sentinel] healthchecks_url` in config.toml to the ping URL.
   Sentinel pings it every 5 minutes once the task is installed.
4. Default URLs (tahomatable.org, hive-log.phone-liaison.workers.dev,
   updawg.co) are in `[sentinel] urls`. After two failures in a row you get
   an ntfy push; you get another when the site recovers.

`megazword sentinel check` is one round (collect + URL checks). The dashboard
Home page has a Sentinel panel.

## Run a task

From the folder you want Mega Zword to use as the project, run:

```text
megazword run "Explain this code and suggest one improvement"
```

Automatic selection rates the prompt easy, medium, or hard, then follows that
level's route and available usage information. It tries another eligible AI
when a run fails or returns no usable answer. You will see which AI it picked
and why. Force one installed tool with `-m`, add this project's notes and
decisions with `-c`, or choose a project with `-p`:

```text
megazword run -m claude -c -p my-app "Review the API"
```

You can also pipe a long prompt through standard input:

```powershell
Get-Content .\task.txt -Raw | megazword run -p my-app
```

`-e` / `--edit` lets a supported AI modify files in the current folder. Review
its changes. On Windows, Grok edit mode is disabled because it has no suitable
write sandbox there. Gemini is read-only and also unavailable in edit mode.

To compare two or three installed tools on the same prompt, use
`--compare` instead of `-m` or `--edit`:

```text
megazword run --compare claude,codex "Compare these two explanations"
```

The calls run at the same time, so this intentionally uses each selected AI.
Mega Zword prints each answer and records each attempt. The dashboard also has
a comparison control. You can vote for the best answer there; votes inform
`megazword advise`, which only suggests a route order and never changes it.

## Chat and project memory

For an interactive conversation, run `megazword chat`. Type at `mz>`; each new
message uses the normal router and includes up to three recent exchanges. Type
`/help` to see the in-chat commands. `/model claude` pins new messages to one
AI; `/auto` restores routing. `/retry` retries the saved answer. `/usage` shows
meters and recent run totals; `/cost` shows rough character-based token counts
for this chat session. `/note text` and `/decide text` save project memory.
`/history` reads it; `/context on` includes it in future prompts, and
`/context off` omits it. `/clear` clears only the chat's recent conversation
context. `/quit`, Ctrl+C at the prompt, or end of input exits.

You can manage memory without opening chat:

```text
megazword note "The service uses JSON" -p my-app
megazword decide "Keep the public API stable" -p my-app --by alex
megazword history -p my-app -n 10
```

## Hive room (group chat)

`megazword room` runs a lightweight group chat between Phil and the bots.
Messages are saved to `~/.megazword/rooms/<room>.jsonl`.

- `megazword room say "your message @claude"`: Post a message. Mentioning `@claude`, `@codex`, `@grok`, or `@gemini` wakes that bot to reply next. Phil's messages always take priority.
- `megazword room show`: View recent messages in the room.
- `megazword room start [--turns 12]`: Run the room turn loop. Stops early if all bots are out of usage or over pace.
- `megazword room stop`: Stop active room turns.
- `megazword room post-summary`: View or post the latest room summary to Q (workshop PR #33).


Notes, decisions and completed runs are saved under
`%USERPROFILE%\.megazword\projects\` on Windows. Pass `-p` to keep projects
separate; otherwise the current folder or repository identifies the project.
`megazword projects` lists projects with memory and recent activity. Include
memory in a one-shot prompt with `-c` or `--context`.

`megazword retry` sends the last saved prompt and rejected answer to a stronger
eligible tool. It skips the previous answerer, unavailable tools and active
out marks. Use `megazword retry -m claude` to request a particular alternative.
Retry has no edit mode and does not restore the previous prompt's edit access.
`quality_check = true` in the config asks the local rating model to flag a weak
automatically selected answer so the usual route can try another tool. It is
off by default, uses local Ollama, and does not check runs where you forced an
AI with `-m`.

## Usage, routes, and suggestions

`megazword usage` shows the available plan meters and Mega Zword run totals.
Claude's meter comes from its usage endpoint; Codex's meter comes from the
latest snapshot in its local session logs; Grok and Gemini use Mega Zword's run
counts because there is no local plan meter. A local run count is not your
remaining subscription quota. The meter can be stale, so check its source and
timestamp when shown. `megazword stats --days 14` summarizes logged runs by day
and AI.

The default routes are in `~/.megazword/config.toml` under `[route]`. An AI at
95% or more may be skipped. When usage is running ahead of its reset clock, it
is reserved for hard tasks. Near a reset, eligible leftover usage may be spent.
An explicit `run -m` is your choice and bypasses automatic route and out-mark
selection. The run log's `est_tokens` is only a rough `(prompt + answer) / 4`
estimate. It is not a provider bill, and it leaves out hidden reasoning, tools,
and some context.

To mark a tool unavailable until its plan resets, use a duration or date:

```text
megazword out grok --until 7d
megazword out codex --until 2026-10-17T23:30
megazword out
megazword out grok --clear
```

When a known provider limit error includes a reset time, Mega Zword can detect
it and mark that tool out automatically. If the provider gives no time, it
uses a one-hour estimate and says so. Other login, network, missing-tool, or
timeout errors do not mark a tool out. A manually forced `-m` run still uses
the AI you named.

`megazword advise` compares recent success, speed, run counts and dashboard
votes, then suggests an order. It does not edit your routes. To apply a change,
review it and edit `[route]` in the config or use Dashboard Settings.

## Dashboard

Run `megazword dashboard`. By default it serves only this PC at
`http://127.0.0.1:8765`, and opens a browser tab. Use `--port`, `-p` or
`--no-browser` to choose another local port, project, or skip opening the tab.
`--app` opens an Edge or Chrome app window when available. Ctrl+C in the
terminal stops the server.

The project selector switches the memory, notes, runs and answers shown. The
page refreshes its state periodically; **Refresh meters** rereads the usage
sources immediately.

- **Run a task:** enter a prompt and send it. Auto selection follows routes and
  pacing; the AI menu forces an installed tool. Check project memory to add
  notes and decisions to the prompt. Compare runs it on two or three chosen
  AIs. A running job shows elapsed time; Cancel stops that job. Answers appear
  when the tool finishes. **Not good enough** retries the last saved answer.
- **Plans & pace:** the bar shows reported usage. The vertical tick shows how
  much of a known reset window has elapsed. If usage is ahead of the tick, the
  plan is being used faster than time passes. Labels identify stale or
  unavailable meters and tools marked out.
- **Routing and suggestions:** the route table shows each difficulty order and
  which tools are unavailable or marked out. Suggestions use recent outcomes
  and votes. They are advice only; use Settings to apply a route change.
- **Runs and trends:** runs by AI covers the last 24 hours; the trend shows
  daily activity. Recent runs lists outcomes, durations, prompt/answer sizes
  and rough token estimates.
- **Compare and votes:** compare answers appear side by side. Vote for the
  answer you prefer; the vote is included in later route advice.
- **Settings:** adjust route order, per-tool timeouts, Claude/Codex/Gemini model
  and effort by task difficulty, log and memory history limits, and the optional
  quality check. Changes are validated and saved to your local config. Blank
  model or effort keeps that CLI's default; blank timeout uses its default.
- **Project memory and past answers:** add a note or decision and inspect saved
  context or the last 50 prompt/answer pairs for the selected project. Copy
  buttons copy an answer when your browser grants clipboard access.

### Phone access over Tailscale

The dashboard can listen on a Tailscale address. Install and sign in to
Tailscale on the PC and phone, then find the PC address with `tailscale ip -4`.
Start the server with that address:

```text
megazword dashboard --host 100.101.102.103
```

Replace the example address. Open the full URL printed in the terminal on the
phone. It contains a per-launch token. Only devices that can reach the PC over
your Tailscale network can use it; anyone with both tailnet access and the link
can run your AIs, so keep the link private. Remote mode requires the token for reads and changes, and
does not launch a browser automatically. The server refuses `0.0.0.0` and `::`.
Use Tailscale rather than exposing the dashboard to the public internet.

The dashboard's remote mode is implemented. Tailscale and Windows OpenSSH
installation and phone sign-in are not configured by Mega Zword. OpenSSH is
needed only for a phone terminal connection, not for the dashboard in a browser.
There is no phone-model answering backend yet.

## Other commands

- `megazword backends` lists supported AI tools and whether they are available.
- `megazword init [--force]` creates a config using installed tools; `--force`
  replaces the existing config.
- `megazword backends` lists CLIs and optional HTTP AIs (openrouter, groq,
  cloudflare, zai, gemini-api, nvidia, mistral). Force one with
  `megazword run "..." -m zai` (they are off the default route).
- `megazword doctor` checks local setup without sending a prompt.
- `megazword export [-p PROJECT] [--since 7d] [--out FILE] [--force]` writes
  project memory, answers and run totals as Markdown. By default it prints to
  the terminal. `--since` accepts a duration such as `14d` or a UTC date.
  Existing output files are kept unless you pass `--force`.
- `megazword import-hive PATH [-p PROJECT]` copies decisions and open handoffs
  from a local Workshop clone into project memory. It leaves the old clone
  unchanged; repeated imports do not add duplicates.
- `megazword --version` prints the installed version. Add `--help` to the main
  command or any command, such as `megazword dashboard --help`, for exact
  options.

## Troubleshooting

Start with `megazword doctor`; each line below matches one of its check names.

| Doctor line | What to check |
|---|---|
| `Python` is FAIL | Install Python 3.11 or newer and reopen the terminal. |
| A CLI says `not on PATH` | Install that tool, sign in, then open a new terminal. At least one of Claude Code, Codex, or Grok is needed. |
| `config: FAIL` | Open `%USERPROFILE%\.megazword\config.toml`; fix its TOML syntax and make each route a list of AI names. If you want a fresh default, save a copy and run `megazword init --force`. |
| `routes: WARN` | Remove misspelled backend names from `[route]`. `megazword backends` shows the supported tools. |
| `out marks: WARN` | List marks with `megazword out`; clear one with `megazword out AI --clear` or correct its reset time in `[out]`. |
| `Ollama: WARN` | Start Ollama. Mega Zword can still rate prompts with its simple fallback rule. |
| `rater model: WARN` | Pull the configured rating model, for example `ollama pull qwen2.5:1.5b`. |
| A provider meter is `WARN` or stale | Reopen/sign in to that tool. Codex's snapshot updates when Codex runs; Grok and Gemini plan quotas are not read directly. |
| `openrouter` / `groq` / `cloudflare` / `zai` / `gemini-api` / `nvidia` / `mistral` key is `WARN` | Set the matching env var (see `.env.example`). Cloudflare also needs `CLOUDFLARE_ACCOUNT_ID`. New terminal after. Keep keys private. These AIs stay off the default route until you add them in `[route]`. `zai`, `gemini-api` and `mistral` train on prompts. |
| `log: FAIL` | Check that your user can write to `%USERPROFILE%\.megazword`. |
| Timeout or network failure during a run | Check the tool login, internet connection and `[timeouts]` in config. Rerun after the issue is fixed. |
| The command is not found from another folder | Open a new terminal after install. Check that pipx's bin folder or `.venv\Scripts` is on your user PATH. |
| Phone cannot open dashboard | Confirm both devices are on the same Tailscale account, use the PC's Tailscale IP, keep the dashboard terminal open, and copy the full token URL from that launch. |

For the available commands and options on this version, use `megazword --help`.
