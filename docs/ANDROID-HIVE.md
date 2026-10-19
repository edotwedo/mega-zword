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
2. [ ] **`phone` lane + PC ping.** Add a `phone` seat to `SEAT_TOKENS` and to
   `PC_SEATS` in `cloud/hive-room/index.js`, so a phone broadcast pings the PC topic.
   Owner: **Fathom-19** (code); Phil adds the key.
   Done when: a post from the `phone` key fires an ntfy PC ping (unit test with a fake
   fetch + a live check after deploy).
3. [phil] **Deploy the Worker** with `NTFY_PC_TOPIC` / `NTFY_PHONE_TOPIC` and the
   `phone` key (`castle/hive-connectors.py` + `wrangler`). Owner: **Phil**.
   Done when: `/app/<phone-key>` loads and a Broadcast wakes a PC seat.
4. [ ] **Broadcast reply convention.** Every live seat replies ONCE to a `Broadcast:`
   message with its designation + current task. Document in `docs/FLOOR.md` and the
   startup AGENTS.md. Owner: **Beacon-17**.
5. [ ] **Fix the usage meters.** `megazword usage` is unreliable (Phil trusts his own
   reading): Gemini shown wrong, agy's Claude/GPT pool confuses the Gemini meter.
   Owner: **Lumen-20** (+ Juniper-16 if it needs the meter code). Done when: `usage`
   matches the provider's own page across two consecutive readings.
6. [ ] **Phone app polish.** Unread badge, optional ntfy subscription link, offline
   cache of the last N messages. Owner: **Lumen-20**.
7. [ ] **Tests + docs.** Keep worker tests green; keep this file and `CLOUD-ROOM.md`
   accurate. Owner: **Lumen-20**.

## Standing assignments

- **Juniper-16**: keep the team-engine scoreboard (ROADMAP #6) moving; help on item 5.
- **Beacon-17**: item 4 + review the phone client and each PR on this branch.
- **Ledger-19**: private lanes unchanged; no Hive work needed.
- **Fathom-19**: item 2 + review the Worker changes.
- **Lumen-20**: items 5, 6, 7 + drive the night.

## Status

- 2026-10-18 ~21:00: phone client coded and pushed (`seat/lumen-20` `26262db`); roadmap
  written; driver loop scheduled hourly until 04:13.
