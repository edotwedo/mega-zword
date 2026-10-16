# Using Mega Zword day to day

Mega Zword is a local command line tool. It routes a prompt to one of your AI
tools, keeps a run log and project memory, and can show the work in a dashboard.
It does not run tasks in the background. Start it when you need it.

## Catch me up when I return

Click **Catch me up** in the dashboard header, or run `megazword brief` in a
terminal. The briefing shows what each reporting session is working on, what it
just finished, blockers and next steps. It reads saved cards without model calls.
Reports older than 30 minutes are marked stale. Missing fields say "not reported";
the feature cannot inspect arbitrary terminal windows or infer their progress.

Mega Zword CLI runs publish start/finish/failure cards automatically. Their
"done" means an answer was returned, not that its claims have been verified.
Use `MEGAZWORD_SEAT` for a stable session name; otherwise the card uses `run-PID`.
Standalone Codex/Claude/Grok sessions publish through Hive MCP's `hive_status`
or this one-line command (replace the example with the session's actual facts):

```powershell
megazword brief report --seat Testlog-14 --project mega-zword --state working --doing "Reviewing the patch" --done "Focused tests passed" --blocked "" --next "Run the full suite"
```

Update on meaningful changes, not in a heartbeat loop. Each report replaces the
previous card, including blank fields. Cards live locally under
`~/.megazword/briefings/`; keep passwords, keys and private details out of them.
Existing MCP sessions need a server reconnect to discover `hive_status`.

For optional camera presence, install from the main checkout using the same Python
environment that runs the dashboard, then restart the dashboard:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[camera]"
```

Open **Catch me up → Enable local camera**. The webcam belongs to the PC running
the dashboard, including when you view it from your phone. Processing uses local
OpenCV face detection; it does not recognize identities, upload frames, save images,
or wake AI sessions. Any detected face can trigger it. Lighting and looking away
can affect detection. After at least 15 seconds with no face and two seconds of
steady presence, the open dashboard displays a briefing. A two-minute cooldown
prevents repeated briefings. It does not inject text into other terminals or speak.

The header shows when the camera is on. **Disable local camera** or close the
dashboard server to release it; closing a browser tab alone does not stop the
server. Camera permission/device failures appear in the dialog. Camera enablement
is never saved across server restarts. The manual button works without OpenCV.

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
or meter is unavailable. Doctor also prints a `Hive:` line pointing at
`megazword floor` (seats) and `megazword floor suggest` (who should take a job).

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

## Jobs

`megazword job plan "add X to Mega Zword"` asks one installed AI to split the
job into pieces (title, files, difficulty, test command). Overlapping files
become one piece. The plan is saved under `~/.megazword/jobs/<id>/job.json`.
Workers that run the pieces are not in this build yet (handoff
`docs/handoffs/2026-10-13-parallel-workers.md`).

## Hive room (group chat)

`megazword room` runs a lightweight group chat between Phil and the bots.
Messages are saved to `~/.megazword/rooms/<room>.jsonl`.

- `megazword room say "your message @claude"`: Post a message. A Phil `@mention`
  picks which one-shot `room start` runs. Mentions from bots are ignored.
  Phil's messages always take priority. Live seats read the log through Hive MCP.
- `megazword room show`: View recent messages in the room.
- `megazword room start [--turns 12]`: One one-shot answers Phil, then it waits.
  Bot `@mentions` do not start more one-shots (those looked like extra live sessions).
  Live seats read the same log through Hive MCP. Stops early if all bots are out
  of usage or over pace.
- `megazword room stop`: Stop active room turns.
- `megazword room post-summary`: Show the latest room summary. Add `--post` to post it to Q (workshop PR #33).

After a session of 3 or more one-shot turns, one bot writes 3-5 short lessons
into the project's memory. `room start` now stops after one turn, so that is
uncommon. Each turn sends a short state card, a rolling summary and the last
few messages, not the whole history, to keep usage down. The dashboard reads and drives the same room
through `/api/room` (view) and `/api/room/say`, `/api/room/start`, `/api/room/pause`
and `/api/room/stop`.

### Hive floor

The floor has one seat per AI: one CLI window each for claude, codex and grok
(gemini when its week is back). HTTP models like groq have no window; they wait
in the Hive.

- `megazword floor`: Show each seat as seated, empty (no key or install) or out, and whether the minimum crew is ready. Saves `~/.megazword/floor.json`.
- `megazword floor introduce [--room hive]`: Post the floor roll call to the room. It has no `@names`, so nobody wakes up until Phil assigns work.
- `megazword floor peek [-n 10]`: Print the latest Hive messages (the shared log).
- `megazword floor wait [--timeout 120]`: Block until a new Hive message lands. Every seat reads the same file; seats still cannot type into each other's CLI windows.
- `megazword floor suggest bulk|edit|decide|review`: Print which seated model should take that kind of job. Empty and out seats are skipped. It prints `(no seat)` and exits 1 when nobody fits. It suggests only; nothing is sent.
  - `megazword floor suggest bulk` → `groq` (first seated HTTP seat: groq, mistral, cloudflare, zai, gemini-api, then any other HTTP seat)
  - `megazword floor suggest edit` → `codex` (then claude)
  - `megazword floor suggest decide` → `claude` (then grok, codex)
  - `megazword floor suggest review` → `claude` (then grok, codex)

### Hive MCP (inside each seat's chat)

`megazword mcp` (or `python -m megazword.mcp_hive`) is a stdio MCP server on
the same Hive log (`~/.megazword/rooms/hive.jsonl`). Tools: `hive_read`,
`hive_say`, `hive_wait`. Register it once in each CLI's own MCP config with
command `megazword` and args `["mcp"]`, and set `MEGAZWORD_SEAT` to that seat's
name (`claude`, `codex`, `grok`) in the same entry. `hive_say` posts as
`$MEGAZWORD_SEAT` (or `bot` if unset), and a seat can't post as `phil`.
`hive_read` and `hive_wait` end with `(after=N)`; pass `after: N` to the next
`hive_wait` (or `floor wait --after N`) so nothing posted in between is missed.
Claude, Codex and Grok call these from inside their own session. This is not
`megazword room start`, which spawns new one-shots. Gemini sits until its week
is back. Groq/Mistral are HTTP stand-ins, not MCP seats.

See `docs/FLOOR.md` for the full layout.


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

Typing plain `megazword` in a terminal opens the Mega Zword app window (the same
as `megazword dashboard --app`) and leaves it running after you close the
terminal. `megazword start` shows the old text start screen. Scripts and pipes
still get the text screen, and so does any run with `MEGAZWORD_NO_APP=1` set.

Each AI can use a different model and effort for easy, medium and hard tasks.
Add blocks like `[claude.hard]` (`model = "opus"`, `effort = "high"`), `[codex.easy]`
(`effort = "low"`) or `[gemini.hard]` to `config.toml`. Anything you leave out
keeps that AI's own default. The run line shows the choice, and `megazword doctor`
lists them.

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
`--app` opens Mega Zword in its own desktop window (pywebview on Windows'
built-in WebView2: no address bar, no browser tabs, MZ icon in the title bar and
taskbar). Closing that window stops the dashboard. Without pywebview
(`pip install pywebview`, or `pip install megazword[app]`) it falls back to an
Edge or Chrome app window. Ctrl+C in the terminal stops the server.

To watch a free bot code, choose its AI in Home, check **code with a free bot**,
and send the task. It edits the folder where you started the dashboard (shown
in the activity panel). Use a dedicated worktree for coding. Compare and Auto
are unavailable in this mode; choose one free API backend.

The job shows the current backend/model, request count, tool activity, edited
files and test outcomes. **Pause** waits for the current request or test to
finish; **Resume** continues. **Send instruction** queues a new direction before
the next operation, including before an already-returned file-write tool call.
For a paused job, send the instruction then resume. **Cancel** kills the run and
its child processes; completed edits remain for inspection.

The coding loop condenses large tool histories to reduce repeated context and
shows rate-limit cooldowns. A cooldown longer than the remaining run cap fails
instead of spending more calls. Paused time does not consume the coding loop's
wall-clock cap. Activity is local under `~/.megazword/run-controls/`, bounded to
40 events per run, with secret values scrubbed. This observes dashboard coding
jobs; it does not attach to independent CLI sessions or restore interrupted jobs.

`megazword app install` puts **Mega Zword** in the Start menu (MZ icon, no
console window); `megazword app remove` takes it out.

The app window has an MZ icon and a compact branded title strip showing the
selected view and project. Its window title follows Home/Hive and the project,
so multiple windows are distinguishable in the task switcher. Edge/Chrome still
owns the native draggable frame and minimize, maximize and close buttons; the
page does not replace these OS controls. Closing the window does not stop a
detached server started by plain `megazword`.

### Home and Hive

Use the sidebar's **Home** and **Hive** buttons to switch views. Home contains
one console transcript above the prompt. **Task options** opens memory, editing
and comparison controls; **Workspace details** opens meters, history and settings.
Hive shows the shared room conversation. **Workers & room details** opens its
roster and status. Enter a message and choose **Send** to start replies.
**Reply controls** contains the turn cap, Pause and Stop. **Pause** waits for the
current reply to finish; **Resume** continues toward the selected turn cap.
**Stop** ends the session. The room is coordination chat, not an editing worker.

**Chats** (sidebar, under Home and Hive): pick an AI (or auto) and press **+** for a
new chat tab. Each tab keeps its AI, project and last few turns across restarts.
Ctrl+Enter sends; **Chat options** contains Rename, New session and Delete chat.
Links: `#hive` opens the Hive, `#tab-t1` opens tab t1. Tabs can't be reordered yet.

### Continuing chat-tab sessions

Claude, Codex and Grok chat tabs save their CLI session ID in `tabs.json` and
resume that conversation, including after an app restart. **session kept** marks
a saved session. Resumed turns send only your new message. If the session is
missing or expired, Mega Zword tries a fresh session once with the tab's recent
history and shows a short note. Login, quota and network errors do not trigger
that retry.

**New session** clears this tab's saved session and recent conversation. It is
disabled while an answer is running. Saved answers remain in answer history.
Auto tabs resume when the answering AI matches the saved session; switching AI
starts with recent history. Free API backends and Gemini keep receiving recent
history; they do not use this CLI-session feature. Grok's installed CLI supports
`--session-id` and `--resume`, so Grok tabs keep real sessions too.

### Home controls

The project selector switches the memory, notes, runs, answers and job output shown. The
page refreshes its state periodically; **Refresh meters** rereads the usage
sources immediately.

- **Run a task:** enter a prompt and send it. Auto selection follows routes and
  pacing; the AI menu forces an installed tool. Check project memory to add
  notes and decisions to the prompt. Compare runs it on two or three chosen
  AIs. A running job shows elapsed time; Cancel stops that job. Answers appear
  when the tool finishes. **Retry** uses the selected project's last saved answer.
  It cannot silently replay another project's task. The CLI equivalent is
  `megazword retry -p PROJECT`; plain CLI `retry` still means the global last run.
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
- **Settings:** adjust route order, per-tool timeouts, log and memory history
  limits, and the optional quality check. Changes are validated and saved to
  your local config. Blank timeout means use the tool's default.
- **Project memory and past answers:** add a note or decision and inspect saved
  context or the last 50 prompt/answer pairs for the selected project. Copy
  buttons copy an answer when your browser grants clipboard access.

### Phone access over Tailscale

Install [Tailscale](https://tailscale.com/download) on the PC and phone and
sign in to the same account on both. Then run on the PC:

```text
megazword dashboard --phone
```

This checks Tailscale and selects the PC's private IPv4 address. If installation,
sign-in or connection is missing, it explains what to do and does not start a server.
It does not install software or change firewall/network settings. For a manual
address, `--host <address>` still works; it cannot be combined with `--phone`.
Keep the terminal open and the PC awake. Open the full URL printed in the terminal on the
phone. It contains a per-launch token. Only devices that can reach the PC over
your Tailscale network can use it; anyone with both tailnet access and the link
can run your AIs, so keep the link private. Remote mode requires the token for reads and changes, and
does not launch a browser automatically. The server refuses `0.0.0.0` and `::`.
Use Tailscale rather than exposing the dashboard to the public internet.

The dashboard's remote mode is implemented. Tailscale and Windows OpenSSH
installation and phone sign-in are not configured by Mega Zword. OpenSSH is
needed only for a phone terminal connection, not for the dashboard in a browser.
There is no phone-model answering backend yet.

## Night Shift

Before calling a model, Night Shift checks the repository's detected test suite
on the starting revision, once per revision per run. A broken baseline leaves
its jobs queued and spends no model usage. Explicit job acceptance commands run
after the edit. Failure output is saved under `~/.megazword/night/test-results/`.
Free HTTP/local coding backends do not need a usage meter; paid fallbacks need
a fresh meter and at least 15% left immediately before being called.

Night Shift does real work while you sleep. It reads `docs/QUEUE.md` on GitHub
(`edotwedo/mega-zword` main) and runs each open line as a job:

1. Reads usage. Free HTTP APIs and Ollama can take jobs without a meter; a 429
   moves to the next free backend. Paid CLIs (Claude, Codex, Grok) stay
   fail-closed: less than 15% left, no meter, or an old reading gets no night
   work. Free backends edit through Mega Zword's coding loop.
2. Makes a fresh copy of the job's repo under `~\.megazword\night\`, never your
   own working folders.
3. The AI with the most room edits files there. If it changes nothing, the next
   AI tries.
4. Mega Zword (not the AI) checks for secrets, commits, runs the tests and
   pushes the branch `night/<date>-<n>`. It never pushes to main.
5. Ticks the boxes in QUEUE.md on one more `night/` branch, then posts one
   summary to Q with no @-tags.

- Run now: `megazword night run` (`--max 3` jobs, `--job-minutes 30` per job,
  `--floor 15` percent). `--max` is how many jobs this run tries, one after
  another (not in parallel). When a job hits the time cap, Mega Zword kills
  the AI CLI and every child it started (the `node` process under Codex's
  `.cmd` shim), marks the job failed, and goes to the next line.
- Turn on every night: `megazword night install --at 01:00 --yes`. It's a
  Windows scheduled task that runs as you, with no window. It only runs while
  you're signed in (a locked PC is fine) and won't start on battery.
- Turn off: `megazword night stop` stops after the current job and skips future
  runs; `megazword night resume` turns it back on. `megazword night remove`
  deletes the scheduled task.
- `megazword night status` shows whether the STOP file is set, whether a run
  is going, the last 10 jobs, and where the last summary is.
- The log is `~\.megazword\night\night.log`; each night's summary is
  `~\.megazword\night\summary-<date>.md`.

## Other commands

- `megazword init [--force]` creates a config using installed tools; `--force`
  replaces the existing config.
- `megazword backends` lists the AI CLIs and optional HTTP AIs (openrouter, groq,
  cloudflare, zai, gemini-api, nvidia, mistral), and whether each is
  available. Force one with
  `megazword run "..." -m zai`. Configured free APIs are included in the default
  routes ahead of paid CLI subscriptions.
- `megazword doctor` checks local setup without sending a prompt.
- `megazword free test` sends one tiny prompt to each configured free identity/API and reachable local Ollama. Use `--provider NAME` to test only one identity; repeat it to select several. Out-marked identities are reported as skipped without a call. `gemini` (Antigravity CLI) and `gemini-api` (Developer API) are separate choices.
- `megazword export [-p PROJECT] [--since 7d] [--out FILE] [--force]` writes
  project memory, answers and run totals as Markdown. By default it prints to
  the terminal. `--since` accepts a duration such as `14d` or a UTC date.
  Existing output files are kept unless you pass `--force`.
- `megazword import-hive PATH [-p PROJECT]` copies decisions and open handoffs
  from a local Workshop clone into project memory. It leaves the old clone
  unchanged; repeated imports do not add duplicates.
- `megazword --version` prints the installed version. `python -m megazword`
  runs the same CLI when `megazword` isn't on PATH. Add `--help` to the main
  command or any command, such as `megazword dashboard --help`, for exact
  options.

## Troubleshooting

Start with `megazword doctor`; each line below matches one of its check names.

| Doctor line | What to check |
|---|---|
| `Python` is FAIL | Install Python 3.11 or newer and reopen the terminal. |
| A CLI says `not on PATH` | Install that tool, sign in, then open a new terminal. At least one of Claude Code, Codex, or Grok is needed. |
| Codex shell calls fail with `CreateProcessAsUserW failed: -1073283067` | On Windows, Mega Zword removes `WindowsApps` and `PowerShell\7` entries from Codex's child PATH so its sandbox uses System32 Windows PowerShell; restart Mega Zword after updating. |
| `config: FAIL` | Open `%USERPROFILE%\.megazword\config.toml`; fix its TOML syntax and make each route a list of AI names. If you want a fresh default, save a copy and run `megazword init --force`. |
| `routes: WARN` | Remove misspelled backend names from `[route]`. `megazword backends` shows the supported tools. |
| `out marks: WARN` | List marks with `megazword out`; clear one with `megazword out AI --clear` or correct its reset time in `[out]`. |
| `Ollama: WARN` | Start Ollama. Mega Zword can still rate prompts with its simple fallback rule. |
| `rater model: WARN` | Pull the configured rating model, for example `ollama pull qwen2.5:1.5b`. |
| A provider meter is `WARN` or stale | Reopen/sign in to that tool. Codex's snapshot updates when Codex runs; Grok and Gemini plan quotas are not read directly. |
| `openrouter` / `groq` / `cloudflare` / `zai` / `gemini-api` / `nvidia` / `mistral` key is `WARN` | Set the matching env var (see `.env.example`). Cloudflare also needs `CLOUDFLARE_ACCOUNT_ID`. New terminal after. Keep keys private. Configured free APIs are tried before paid CLI subscriptions at every difficulty. `gemini-api` and `mistral` train on prompts. |
| `log: FAIL` | Check that your user can write to `%USERPROFILE%\.megazword`. |
| Timeout or network failure during a run | Check the tool login, internet connection and `[timeouts]` in config. Rerun after the issue is fixed. |
| The command is not found from another folder | Open a new terminal after install. Check that pipx's bin folder or `.venv\Scripts` is on your user PATH. |
| Phone cannot open dashboard | Confirm both devices are on the same Tailscale account, use the PC's Tailscale IP, keep the dashboard terminal open, and copy the full token URL from that launch. |

For the available commands and options on this version, use `megazword --help`.

## Free AIs that code

### Quick start

Set only the provider keys you have. In PowerShell, replace each placeholder and
open a new terminal after running `setx`:

```powershell
setx OPENROUTER_API_KEY "<your-key>"
setx GROQ_API_KEY "<your-key>"
setx GOOGLE_AI_API_KEY "<your-key>"
setx MISTRAL_API_KEY "<your-key>"
setx ZAI_API_KEY "<your-key>"
setx NVIDIA_API_KEY "<your-key>"
setx CLOUDFLARE_API_TOKEN "<your-token>"
setx CLOUDFLARE_ACCOUNT_ID "<your-account-id>"
```

Check one provider, then give it a coding task:

```powershell
megazword free test --provider groq
megazword run -e -m groq "Fix the failing test in this folder, run tests, and summarize the change."
```

For OpenRouter's changing free catalog, list models currently advertised at
zero price with tool support before choosing an ID:

```powershell
megazword free models
```

This reads the public catalog without making an inference request. A listed
model can still be throttled, unavailable to this app, or unable to complete a
coding task; verify it with a bounded coding run before relying on it.

To try one listed model directly, set its exact ID in your user config:

```toml
[free.openrouter]
model = "google/gemma-4-31b-it:free"
```

Then run `megazword free test --provider openrouter` and, if it responds,
`megazword run -e -m openrouter "Fix the failing test in this folder."`.
Replace the sample ID with one from the live list; this setting overrides the
default free router.

`gemini-api` is the Google AI Studio API; `gemini` is the separate Gemini CLI
identity. Ollama runs locally and needs no API key. The default free coding
failover order is OpenRouter, Groq, Cloudflare, Z.AI, Gemini API, Mistral,
NVIDIA, then Ollama. Mega Zword skips missing or marked-out providers. It waits
between calls to respect each provider's configured pacing (Groq: 2 seconds;
OpenRouter: 3; Gemini API: 6).

Groq's GPT-OSS coding requests include its required parsed reasoning format.
Groq offers a Free plan with rate limits, while its Developer plan bills GPT-OSS
by token; check the account tier in Groq Console if avoiding any possible API
charge. Mega Zword cannot determine that billing tier from the API key.

The verified Groq roster also includes `groq-120b`, `groq-qwen` (Qwen 3.8
27B), and `groq-allam` (Allam 2 7B). Groq's Free-plan request limits are per
model; the coding loop reads the remaining-request headers and changes models
when 5% or fewer remain. The low-quota marker carries across runs until the
provider's reset header expires it. All four identities use the same API key and share a
conservative request pace. Run `megazword free test --provider groq-qwen` to
check one identity. Gemini API `gemini-api-31-lite` selects the verified
Gemini 3.1 Flash-Lite model; it remains distinct from the `gemini` CLI identity.
See [the live-tested roster](FREE-MODEL-ROSTER.md) for the current quotas,
shared-pool cautions and multilingual candidates.

OpenRouter's dynamic `openrouter` route selects a current free model. Five
fixed OpenRouter identities also passed a required-tool probe:
`openrouter-dots`, `openrouter-nemotron-nano`,
`openrouter-nemotron-lightning`, `openrouter-laguna-s`, and
`openrouter-laguna-xs`. They share the same daily request pool and are placed
after independent free providers in automatic fallback. For example:

```powershell
megazword free test --provider openrouter-nemotron-lightning
megazword run -e -m openrouter-laguna-s "Fix the failing test in this folder."
```

**Cerebras is optional and not in automatic free routing.** Create a key at
[cloud.cerebras.ai](https://cloud.cerebras.ai). Current pricing offers a $5
starter credit, then pay-as-you-go. To opt in, set `CEREBRAS_API_KEY` and
select `-m cerebras`; check the balance and pricing first. The default model is
`qwen-3.8-27b`, which supports multi-turn tool use. No key is configured here
and no live request has been sent.

On a rate limit (HTTP 429), Mega Zword uses the provider's `Retry-After` when
available, marks that backend out until the reset, and tries another free
backend. If the mark is stale, clear it with `megazword out groq --clear`.
After editing tests, the quality gate requires a non-constant assertion or
`pytest.raises` and a call to imported production code. This is a structural
check, not proof the test is correct; review the changes and run the project's
tests.

### OpenRouter model aliases

Sign in with Google at [openrouter.ai](https://openrouter.ai), open **Keys**,
then **Create Key**. Keep the key private. Save it in PowerShell:

```powershell
setx OPENROUTER_API_KEY "paste-your-key-here"
```

Open a new terminal. One key enables `kimi`, `deepseek`, `qwen-coder` and
`openrouter`. The current free catalog is routed by `openrouter`:

```powershell
megazword run -m openrouter "Explain this function"
megazword run -e -m openrouter "Fix the failing test in this folder"
```

Those aliases need a current model ID configured before use. For a model chosen
from OpenRouter's current free catalog, use the `openrouter` identity instead:

```powershell
megazword run -m openrouter "Explain this function"
megazword run -e -m openrouter "Fix the failing test in this folder"
```

These names use OpenRouter model IDs saved in `~/.megazword/config.toml`.
OpenRouter changes its free catalog often. As of 2026-10-15, the configured
Kimi K2.6, DeepSeek V3.1 and Qwen3 Coder `:free` IDs were absent from its live
model catalog, and Qwen Coder returned HTTP 404. Check for a current `$0`
model with tool support before setting an override; a model name without
`:free` may spend OpenRouter credit.

For example, update an alias only after confirming its current free ID:

```toml
[free.kimi]
model = "<current-free-model-id>"
[free.deepseek]
model = "<current-free-model-id>"
[free.qwen-coder]
model = "<current-free-model-id>"
```

Check the exact ID and price at
[openrouter.ai/models](https://openrouter.ai/models). `megazword free test`
checks configured identities but cannot reserve provider capacity; a free
endpoint may still rate-limit or disappear.

Before an OpenRouter request from `megazword free test`, Mega Zword checks that
the configured model is still listed at zero price with tool support. Stale or
unverified IDs are skipped with an explanation, which avoids 404 retries and
accidental paid requests from this free-provider check.

These three backends are marked as training on data conservatively: an unknown
serving-provider policy counts as `True`, so prompts and file results are scrubbed.
[OpenRouter's privacy policy](https://openrouter.ai/privacy/) explains that data
practices vary by serving provider. Check your OpenRouter privacy settings and
the chosen provider's policy. A scrub cannot guarantee removal of all private data.

### Coding loop and automatic failover

Free API models can edit files through Mega Zword's own coding loop:

```powershell
megazword run -e -m groq "Fix the failing test in this folder. Run tests and summarize the change."
```

Set the provider's API key as described in Quick start above. This also works with `openrouter`,
`kimi`, `deepseek`, `qwen-coder`, `gemini-api`, `mistral`, `cloudflare`, `zai`, and `nvidia`. Availability and quota
still depend on the provider. The coding loop has been live-verified with Groq's
GPT-OSS 20B and several other free API and local backends.
For local Ollama, pull the configured model, then use `-m ollama`. Its default is
`qwen2.5-coder:7b`; change it under `[free.ollama]` with `model = "your-model"`.
If that model is missing, the coding loop uses the first installed model reported
by Ollama and prints its name.

With just `-e`, the normal route picks the AI. API models on that route use the
coding loop. Claude, Codex and Grok keep their existing CLI paths and restrictions.

The loop can list, read, write and replace files, run one configured test command,
and finish with a summary. Replacements must match once. It refuses paths outside
the current folder, `.git`, `.env` files and hard links. It never commits. It prints
the summary and `git diff --stat`; new untracked files do not appear in that stat.
Review the files after a run, including one that stops early.
After an edit, a passing test command ends the run successfully, subject to the
test quality gate and optional review below. Three identical
tool calls in a row prompt the model to finish. Edits to `test_*.py`, `*_test.py`
and files under `tests/` require the job to mention tests.

On an API failure (including 429 or a timeout), the coding loop tries the next
available free backend within the same run, even when you select one with `-m`.
The default order after the selected backend is OpenRouter, Groq, Cloudflare,
Z.AI, Gemini API, Mistral, NVIDIA, then Ollama. Configure `[agent].failover_order`
to change it. Missing keys, unavailable local Ollama and backends marked out in
config are skipped. Each backend is tried at most once in this order. The task,
tool observations, current files, test results and quality gate carry forward;
the step and wall-clock caps do not reset.
The terminal reports each switch. CLI coders keep their usual routing.
When there are no remaining fallback candidates, 429, 500, 502 and 503 retain
the three retries after 2, 5 and 10 seconds. Tool-format rejections first try the
existing JSON protocol. Test failures and reviewer rejection do not cause a switch.

Native tool calls are preferred. If the provider rejects them or the model replies
with text, the loop switches to JSON tool replies. Set `text_protocol = true` to
start with JSON. Models that train on data receive the existing secret scrub on
prompts and file/test results before every call.

Optional settings in `~/.megazword/config.toml`:

```toml
[agent]
# [] disables automatic backend switching. Only free/API/local backend names.
failover_order = ["openrouter", "groq", "cloudflare", "zai", "gemini-api", "mistral", "nvidia", "ollama"]
max_steps = 30
max_chars = 12000
call_timeout = 60
wall_timeout = 600
test_timeout = 120
text_protocol = false
test_command = ["python", "-m", "pytest", "-q", "-x"]
# Optional; unset or empty disables review.
reviewer = ""

[agent.pace]
gemini-api = 6
mistral = 2
groq = 2
cloudflare = 1
openrouter = 3
nvidia = 2
zai = 2
ollama = 0
```

Pacing is the minimum number of seconds between call starts for each provider,
including retries. Workers share timestamps and locks under
`MEGAZWORD_HOME/agent-pace` (normally `~/.megazword/agent-pace`); different models
on the same provider share the gap. Zero disables pacing. Waiting uses the run's
wall time cap; an unavailable lock stops the run instead of sending a burst.

New or changed Python tests must contain a nonconstant assertion or
`pytest.raises`, and call imported production code directly or through a helper
or fixture. Both explicit finish and passing tests go through this check.
Rejection gives the model the file, test and reason, then continues within the
same step and time caps. This static check catches empty/constant tests; it does
not prove that a test covers the requested behavior. Tests using dynamic imports,
custom assertion helpers or unusual fixture wiring may need a simpler structure.

Set `reviewer = "groq"` (or another available backend) to review the complete diff
of files edited by the loop, including new files, once before success. API/local
reviewers receive no tools; CLI reviewers use the normal non-edit backend.
The reviewer must reply `ACCEPT` or `REJECT` with a reason. Rejection, an invalid
answer, or reviewer failure fails the run and leaves the edits for inspection.
Diffs above 200,000 characters fail rather than receiving an incomplete review.

The model cannot change the test command or add shell commands. Set the command
yourself for the project. Tests execute project code with your normal permissions;
the file tools' path rules do not sandbox that code. Each call's timeout is also
bounded by the time left in the run and the backend's `[timeouts]` setting.
Runs stop on a cap or error and leave edits for review. The normal run log records
the request count, backend switch history, requests by backend and estimated tokens.
Stats count those model requests and use
the coding run's final outcome for their success rate.
