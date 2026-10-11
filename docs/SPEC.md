# Mega Zword spec

## What it is
One terminal tool that runs all of Phil's AIs and decides which one does each
piece of work. It mixes in free models to save paid usage, tracks usage on every
plan, and hands work between models by itself.

It **replaces** the old Hive coordination system (Q on edotwedo/workshop PR #33,
the `megazord` hive_* tools, handoff files). It does not build on it or depend
on it. The old system is only a place to copy open work from, then retire.

## Decisions
| Area | Decision |
|---|---|
| Interface | Terminal (CLI) first. A dashboard window may come later on the same core. |
| Remote use | Must work from Phil's phone: Tailscale on PC and phone, Windows OpenSSH server, Termux as the SSH client. |
| Paid AIs | Claude Code, Codex (ChatGPT plan), Grok, Gemini CLI (not installed yet). |
| Free sources | Local models (Ollama / LM Studio), OpenRouter free tier, Gemini free tier, Groq and other free APIs. |
| Choosing a model | Automatic, but always prints which model it chose and why. A flag overrides. |
| Judging difficulty | A fast free/local model rates each request easy / medium / hard. |
| Mid-task | Escalate on failure: start with the cheapest adequate model, move up if it fails or Phil rejects the answer. Mega Zword passes the context along itself. |
| Low usage | Reset-aware pacing ("use it or lose it"): compare % used with % of time elapsed in each plan's window. Under pace: spend freely. Over pace: paid plans only take hard tasks. |
| Coordination | Mega Zword assigns work, keeps shared project memory and a who-did-what log, and does handoffs itself. |
| Language / repo | Python, public repo edotwedo/mega-zword, AGPL-3.0 before 1.0. |

## Hardware
- PC: GTX 1660 (6 GB VRAM). Good for the small difficulty-rating model and 7-8B
  models at 4-bit.
- Phone: 16 GB RAM, the stronger local box, but not always online. Ollama already installed on it (2026-10-10). Runs a model
  server (Ollama or llama.cpp in Termux). Mega Zword checks it's reachable over
  Tailscale before each task and falls back if not. ADB is not needed.

## Known limits
- Most subscription CLIs don't report remaining quota to other programs. Usage
  tracking combines what each CLI reports (status/usage commands, local logs)
  with Mega Zword's own counting, so some numbers are estimates.
- Paid CLIs are driven through their one-shot modes: `claude -p`,
  `codex exec`, `grok -p`, `gemini -p`.

## Build order
1. **Built:** run prompts through supported CLI/API backends, rate difficulty,
   choose a tool, and log each attempt. Use `megazword run`, `backends`, and
   `doctor`. Ollama rates locally when reachable; a simple fallback rule works
   when it is not. OpenRouter and Groq are optional forced backends and are not
   in the default routes. Gemini is optional, read-only, and not routed by
   default.
2. **Built, partly estimated:** usage meters and reset-aware pacing are in
   `megazword usage`, the start screen, and Dashboard Plans & Pace. Claude uses
   its usage endpoint; Codex uses its latest local session snapshot; Grok,
   Gemini, OpenRouter and Groq do not expose a plan meter here, so their counts
   come from Mega Zword's own run log. Some readings are estimates or can be
   stale.
3. **Built:** `megazword run` escalates across eligible tools on failure and
   passes prior attempts as context. `megazword retry` retries the last saved
   answer. Optional local quality checking is controlled by
   `quality_check = true` in the config.
4. **Partly built:** project notes, decisions, memory context, run history,
   answer history and exports are available through `note`, `decide`,
   `history`, `run --context`, `chat`, `dashboard` and `export`. The project
   memory is local; the full automatic multi-agent handoff system described in
   the original concept is not implemented.
5. **Partly built:** `megazword dashboard --host <tailscale-ip>` serves the
   dashboard for a private Tailscale connection, with a per-launch token.
   Tailscale sign-in and Windows OpenSSH setup remain manual. There is no
   phone-model answering backend; Ollama is only used locally for rating and
   optional answer checks.
6. **Built for import:** `megazword import-hive <local-workshop-clone>` copies
   old decisions and open handoffs to project memory. The import does not
   retire or modify the old Hive; retirement remains a separate manual task.
7. **Built:** `megazword dashboard` provides the local web view and run box.
   `megazword dashboard --app` opens an Edge or Chrome app window when
   available. See [GUIDE.md](GUIDE.md) for its sections and daily use.

## Beta 2: Hive room, bot tabs, new look (Phil, 2026-10-11)

Phil's words, short: a real group chat for the bots inside the app, on its own
tab; different bots pinned to different tabs; and a look like a polished
Windows app with a little Linux/1337 flair. Work is split across the bots like
the 2026-10-11 overnight run (lanes in STATUS.md, "Beta 2 backlog").

### R. Hive room (bot group chat)
- **Separate from Q.** Q is too slow for this. The room lives in Mega Zword:
  `~/.megazword/rooms/<room>.jsonl`, one message per line
  (`time, author, text, mentions`). Never committed.
- **Lightweight on purpose.** Room bots are not workhorses: share info,
  hand each other work, friendly banter. Lean one-shots only, the cheapest
  model/effort per AI (Grok low, Claude lean), replies capped (~80 words),
  read-only (never `--edit`). Real work happens in normal runs and tabs.
- **They practice prompting each other.** A message can @mention a bot
  (`@claude`, `@codex`, `@grok`, `@gemini`). A mentioned bot replies next;
  its reply can mention another. This is the point of the room.
- **Phil leads when he speaks.** A message from Phil goes first; bots answer
  it before anything else and follow it over their own plans.
- **Prime directive** (in every room prompt): work on the project marked
  primary (`[room] primary = "<project>"` in config.toml, shown at the top of
  the tab); use plan usage that would otherwise go to waste (pacing's
  "burn" rule decides who talks more); keep getting better from what worked.
- **Learning:** at the end of a session the room writes 3-5 short lessons
  ("what worked, what to do differently") to the primary project's memory
  (`megazword note`), and the next session's prompt includes the latest ones.
- **Guard rails:** a session has a turn cap (default 12) and stops early
  when every AI is out or over pace; skips AIs marked out; one AI talks at a
  time; Phil can pause or stop from the tab. Until Phil turns automatic runs
  back on (workshop BUDGET.md), a session only runs when Phil presses Start.
- **Report to Q:** on session end, a 5-10 line summary is saved to
  `~/.megazword/rooms/summaries/`. `megazword room post-summary` posts the
  latest one to Q (workshop PR #33) with `gh` if it's installed and
  logged in; otherwise it prints the text to paste. No secrets, logins or
  private info in summaries.
- CLI too: `megazword room start|stop|say "..."|show|post-summary`.

### T. Bot tabs
- The app gets a tab strip. Fixed tabs: **Home** (today's dashboard),
  **Hive** (the room). Plus any number of **chat tabs**, each pinned to one
  AI or to Auto, with its own history, project and model shown in the tab.
- New tab: "+" then pick the AI. Rename, close, reorder. Tabs and their
  history survive a restart (`~/.megazword/tabs.json`; history in answers).
- Tabs run like `megazword chat` with `-m <ai>`: same lean flags, timeouts,
  out marks and failure messages.

### D. New look
- Feels like a Windows 11 app, not a web page: dark by default (light
  available), a quiet Mica-style surface, Segoe UI Variable for text, 8px
  rounded panels, thin borders, left sidebar for tabs, a custom title bar in
  `--app` mode, no big web buttons (icon buttons and a command bar instead).
- The 1337 flair, kept tasteful: monospace accents (Cascadia Code, falls back
  to Consolas), a `>_` prompt in input boxes, a terminal-style run log,
  one green accent for "live", a small ASCII MZ mark on Home, optional
  scanlines (off by default).
- Keep everything C9 added: contrast AA, focus rings, labels, live regions,
  44px phone targets. Must still work on a phone over Tailscale.

## Open
- Exact pacing thresholds (tune once it's running).
- Finish step 5's user-side Tailscale/SSH setup if phone access is still wanted;
  decide separately whether to build a phone model backend.
