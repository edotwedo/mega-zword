# Android Hive client + overnight work (Lumen-20 owns)

Phil, 2026-10-18: direct access to the Hive from Android — send a broadcast, get a
reply from every live seat, reply back, with no third-party chat app. Lumen-20 owns
this until ~05:00, then hands off.

## Rules for the night (Phil)

- Keep work going until ~05:00.
- **Never drain a bot's usage.** Treat ~20% as the floor: do not assign or run heavy
  work on a seat under 25%, and stop a seat near 20%.
- Fewest tokens, same message (AGENTS.md priority 1).

## Roadmap

1. [x] **Phone client page at `/app/<key>`** — read + post + Broadcast, same-origin,
   strict CSP, key never baked into the page. Lumen-20, `26262db`; worker tests 32/32.
2. [x] **`phone` lane + PC ping.** `phone` is in `PHIL_LANES` in
   `cloud/hive-room/index.js`, so a phone post pings the PC topic. Lumen-20,
   `545f458`; unit test with a fake fetch. A dedicated `phone` key is optional —
   Phil's phone posts on the `phil` lane today.
3. [x] **Deploy the Worker.** Lumen-20 deployed it after clearing the stale
   `CLOUDFLARE_API_TOKEN` env var (it blocked OAuth and lacked access; error 9109).
   Live at version `38e23a24`; `NTFY_PC_TOPIC` / `NTFY_PHONE_TOPIC` set.
   Done: `/app/<key>` returns 401 only without a key, and a phone post pings the PC.
4. [x] **Broadcast reply convention.** Every live seat replies ONCE to a `Broadcast:`
   message with its designation + current task. Document in `docs/FLOOR.md` and the
   startup AGENTS.md. Owner: **Beacon-17**. Done 2026-10-19 (Beacon-17): FLOOR.md Broadcast section (only Phil's lanes call a roll call; reply format) + workshop AGENTS.md.
5. [x] **Fix the usage meters.** `megazword usage` is unreliable (Phil trusts his own
   reading): Gemini shown wrong, agy's Claude/GPT pool confuses the Gemini meter.
   Owner: **Lumen-20** (+ Juniper-16 if it needs the meter code). Done when: `usage`
   matches the provider's own page across two consecutive readings.
   Status 2026-10-18 22:15: **verified live.** agy's own panel and `megazword usage`
   agree (Gemini 82.69% remaining = 17.31% used); the parser counts only the Gemini
   group and shows the Claude/GPT pool separately. Regression test with the verbatim
   payload added. Second reading at 23:15 matched again (agy 17.31% vs meter 17%),
   so item 5 is done.
6. [x] **Phone app polish.** Unread badge (counts new messages while the page is
   hidden, clears when you look at it) and an offline cache of the last 200 messages
   in `localStorage`, restored on load. Owner: **Lumen-20**.
   Left for later: an ntfy subscribe link (needs the topic passed to the page).
7. [~] **Tests + docs.** Keep worker tests green; keep this file, `CLOUD-ROOM.md` and
   `HIVE-ROSTER.md` accurate. Owner: **Lumen-20**.

## Standing assignments

- **Juniper-16**: keep the team-engine scoreboard (ROADMAP #6) moving; help on item 5.
- **Beacon-17**: item 4 + review the phone client and each PR on this branch.
- **Ledger-19**: private lanes unchanged; no Hive work needed.
- **Fathom-19**: item 2 + review the Worker changes.
- **Lumen-20**: items 5, 6, 7 + drive the night.

## Status

- 2026-10-18 ~21:00: phone client coded and pushed (`seat/lumen-20` `26262db`); roadmap
  written; driver loop scheduled hourly until 04:13.
- 2026-10-18 22:15 (driver pass 1): usage meters verified against agy's own panel;
  regression test added. No seat has claimed a branch yet in the room.
- 2026-10-18 23:15 (driver pass 2): meter matched a second reading -> item 5 done.
  Item 6 (phone-app polish) landed as `9eea45f`. Still no seat claims.
- 2026-10-19 00:15 (driver pass 3): items 2, 3, 4 closed (phone lane, deploy, Broadcast
  rule). All seats replied to Phil's phone test. room_wait wired + per-seat bookmarks
  (`ebf3573`). Remaining: item 7 (tests/docs) and Phil restarting sessions to load the
  participation rules.
