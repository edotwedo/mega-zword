# Release notes

## Beta 3.0 (not tagged yet)

Not released yet. The installed version is still `0.1.0b1` until the lead
bumps it and tags `v0.3.0-beta.1` (STATUS, Beta 3.0 items 4-5). Sources:
README "What's new in Beta 3.0", `docs/GUIDE.md`, `docs/FLOOR.md`,
`docs/STATUS.md`.

### Hive floor and MCP

- `megazword floor` lists one seat per AI (seated, empty or out), says whether
  the crew is ready (claude, codex and grok seated or marked out), and writes
  `~/.megazword/floor.json`.
- `floor introduce` posts the roster to the Hive room without `@names`, so no
  AI starts working until Phil gives it a job. `floor peek` and
  `floor wait [--after N]` read the shared log.
- `megazword mcp` (or `python -m megazword.mcp_hive`) is a stdio MCP server
  with the tools `hive_read`, `hive_say` and `hive_wait`. Add it to each CLI's
  MCP config (command `megazword`, args `["mcp"]`) and set `MEGAZWORD_SEAT`.
  A seat cannot post as `phil`. Pass the `(after=N)` value from a read to the
  next wait so no message is missed.
- `scripts/hive_up.ps1` opens the app and one Windows Terminal tab per main
  CLI (`-Skip` for a seat you already have open).
- `doctor` prints a `Hive:` line that points to the floor commands.

### Usage meters

- Plan meters appear on the start screen, in `megazword usage` and in the
  dashboard, and all three use the same summary. Each meter shows how old its
  snapshot is and when an AI is out.
- Claude uses Anthropic's usage endpoint (unofficial). Codex reads its session
  log snapshot. Grok reads its CLI billing log. Gemini reads
  `agy -p /usage`.
- `megazword plan` ranks the AIs by spare usage, so you can pick who takes new
  work.

### Hive room

- `megazword room say|start|stop|show|post-summary` runs a group chat between
  Phil and the AIs. An `@mention` picks who answers next, and Phil's messages
  always come first.
- Each turn is a short one-shot call: a state card, a rolling summary and the
  last few messages. A session stops at the turn cap (default 12) or when every
  AI is out of usage. Only one session can run in a room at a time.
- After a session of 3 or more turns, one AI writes 3-5 lessons into project
  memory.
- The dashboard Hive view has Send, Start, Pause, Resume and Stop
  (`/api/room*`). `post-summary` only prints unless you add `--post`.

### Chat tabs

- The dashboard sidebar has a **Chats** list. Each tab has its own AI (or auto
  routing), project and recent history, and tabs are kept across restarts
  (`/api/tabs`).
- Ctrl+Enter sends. You can rename a tab, and closing one takes two clicks.
  Deep links: `#hive`, `#tab-t1`. Tabs can't be reordered yet.

### Sentinel

- `megazword sentinel status|log|check` records reboots, logins and network
  drops in `sentinel.jsonl`. It uses no AI usage. The Home page has a Sentinel
  panel.
- Optional alerts: an ntfy push after two URL check failures in a row and
  another on recovery, plus a healthchecks.io ping. The 5-minute scheduled task
  is created only by `megazword sentinel install --yes` (Phil's call).

### Free HTTP backends

- Supported backends: OpenRouter, Groq, Cloudflare Workers AI, Z.ai, Google AI
  Studio (`gemini-api`, default model `gemini-flash-latest`), NVIDIA NIM and
  Mistral. Keys come from environment variables (on Windows, missing keys are
  filled from the User environment). `.env` files are not loaded.
- None of them are in a default route except Mistral, which goes first in
  `easy` once `MISTRAL_API_KEY` is set. All are left out of `--edit`.
- `megazword backends` marks the providers that train on prompts (Mistral
  free tier, Google AI Studio unpaid). Before a prompt goes to one of them,
  obvious secrets and private-folder paths are removed, and the run is logged
  with `trains_on_data`.

### Conductor (`floor suggest`)

- `megazword floor suggest bulk|edit|decide|review` names the seated model
  that should take a job. It only suggests and never sends anything.
  - bulk: groq, mistral, cloudflare, zai, gemini-api, then other HTTP seats
    (never a CLI)
  - edit: codex, claude
  - decide and review: claude, grok, codex
- Empty and out seats are skipped. If no seat fits, it prints `(no seat)` and
  exits with code 1.

### Also since Beta 1

- Plain `megazword` opens the app window. `megazword start` shows the text
  start screen.
- The native app window uses pywebview (extra `[app]`) with an MZ icon.
  `megazword app install|remove` adds or removes the Start menu shortcut.
- New dashboard look, with Home and Hive views. `--phone` connects over
  Tailscale.
- Per-level model and effort settings for each CLI: `[claude|codex|gemini.<level>]`.
- AI CLIs start with a hidden console on Windows.

### Known gaps

- Gemini (agy) is out until Oct 18. Groq returned 403 on 2026-10-12.
- No standalone `.exe`. Calendar (B10/B11) is parked.
