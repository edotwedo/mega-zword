# Handoff: the Hive room moves to Cloudflare (ROADMAP #5)

- **Status:** built and merged 2026-10-17; waiting on Phil to deploy, then the PC/cloud exchange test and the startup-rule switch
- **Written by:** Beacon-17 (Claude Code), 2026-10-17, at Phil's request ("um ok do that")
- **Why:** Mega Zword was meant to replace Q (decided 2026-10-10). The room works on the PC, but cloud bots
  (Claude cloud, Codex cloud) can't reach a file on Phil's PC, so everyone drifted back to Q. Phil: "we need a
  real option, just 'they'll get it sometimes' is not gonna work." He also found the old room buggy, with one
  bot in it that "only seemed to belong to the chat."

## Decision (Phil, 2026-10-17)
One room hosted on Phil's Cloudflare account (free plan): a Worker plus storage. Every seat (PC, cloud, phone)
reads and posts there over HTTPS. No tunnel into the PC, no second copy to sync. When it works, Q becomes a
read-only archive (PR #33 stays open, never merged or closed).

## Build (Codex)
1. **Worker** in `cloud/hive-room/` (plain JS, no framework):
   - `GET /rooms/<room>/messages?since=<id>&limit=<n>` returns JSON messages, oldest first.
   - `POST /rooms/<room>/messages` with `{"text": "..."}` posts one message.
   - Every request needs `Authorization: Bearer <seat token>`. The **server** maps token to seat name
     (store only SHA-256 hashes, in a Worker secret such as `SEAT_TOKENS` = `{"<sha256>": "beacon-17", ...}`),
     so nobody can post as someone else. A read-only token kind is fine for viewers.
   - Plain text only, max 4,000 characters, a per-seat rate limit (about 30 a minute), room names `[a-z0-9-]`.
   - Storage: D1 or KV. **Check Cloudflare's own docs for the current free-plan limits first** (D1 started
     enforcing free daily limits on 2026-09-01) and pick what fits a few hundred messages a day with headroom.
     Write the numbers and links in `cloud/hive-room/README.md`.
   - Tests with `node --test` against the handler with a fake store (no network, no Cloudflare account).
2. **Mega Zword side** (`src/megazword/room.py` and the CLI):
   - If a room URL is configured, `room say/show` go to the Worker; the seat token comes from Keymaster
     (Credential Manager), never from a file in the repo or a prompt.
   - Keep the local file as a cache. If the Worker can't be reached, `show` reads the cache and says so;
     `say` queues locally and sends next time. No silent loss.
   - Fix: `megazword room show` crashes on emoji on Windows (`UnicodeEncodeError` from cp1252). Print UTF-8 or replace.
   - **No house bot.** Find whatever auto-replies in the room and switch it off; only real seats post.
   - Stop automatic room-summary posts to Q (they looped and @-mentioned the Codex connector on 2026-10-16).
     Keep `post-summary` as a manual command only.
   - Tests with a fake HTTP server or fake client.
3. **Docs:** `docs/CLOUD-ROOM.md` for any bot: the URL, curl examples to read and post, how a cloud session gets
   its token (Phil puts it in that environment's secret settings, never in Q or GitHub), and which host to
   allow in the cloud environment's network settings.
4. **Deploy script for Phil:** `cloud/hive-room/deploy.ps1`, which creates the storage, deploys, and makes the
   seat tokens (prints each token once, saves hashes as the secret). Phil runs it; bots don't deploy.

Run the full test suite before pushing. Push to the branch on local Gitea `origin`, not GitHub.

## Phil's part (after the build)
1. Run `cloud/hive-room/deploy.ps1` (one paste).
2. Put each cloud bot's token in that cloud environment's secrets, and allow the Worker's address in its network settings.

## Claude's part (after Phil deploys)
Review the branch, merge it, then change the startup rules (workshop AGENTS.md, mega-zword AGENTS.md, Phil's
global CLAUDE.md) from "read Q" to "read the room," and mark Q archived.

## Done when
A PC seat and a cloud seat each post a message and read the other's, through the Worker; `room show` handles
emoji; nothing auto-posts to Q; the startup rules point at the room.

## Report (Beacon-17, 2026-10-17)
- **Built by Cirrus-17 (Codex) through `megazword run -m codex -e`.** Mega Zword stopped waiting at its 600 s
  Codex limit, but Codex had finished the code; Beacon-17 saved it (44b41e7) and checked it.
- **Worker** (`cloud/hive-room/`): D1, chosen after Cloudflare's own free-plan numbers (README has them and
  links). Server maps hashed tokens to lanes, read-only tokens, 32 KB body cap, 4,000 characters, 30 a minute
  per lane, retry keys stop duplicates. 9 node tests pass.
- **Mega Zword:** remote room with local cache and a send queue that never drops a message; HTTPS only, the
  token is never sent to a redirect; emoji crash fixed; `room start` retired (no house bot); no automatic Q posts.
- **Review changes by Beacon-17:** deploy defaults now one token per lane (phil, claude-pc, codex-pc, grok-pc,
  claude-cloud, codex-cloud), since session names change every chat; the dashboard test now expects no house-bot
  start.
- **Tests:** full suite 1440 passed, 2 failed before the fixes: the dashboard house-bot test (expected, fixed)
  and `test_live_check::test_full_check_on_fakes`, which passes alone on this branch and on main (timing flake
  under full-suite load). Affected files after the fix: 67 passed.
- **Left:** Phil deploys; a PC seat and a cloud seat exchange a message; then the startup rules move from Q to the room.
- **Mega Zword note:** its 600 s Codex limit is short for build jobs (`[timeouts] codex` in config.toml).
