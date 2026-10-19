# Inspiration roadmap (Lumen-20 owns, 2026-10-19)

Source: `docs/INSPIRATION.md` (Beacon-17, 18 systems, top five). Ordered by value to
the failures we actually hit tonight, not by how clever the analogy is.

Rules: one item per driver pass; small diffs; tests; land on main. Never drain a seat
(20% floor). If another Command Code instance claims an item, do not touch its files.

## Now

1. [x] **Erlang restart window (#11).** 3 failures in 10 minutes stops a job and posts
   to Phil instead of riding it to the step cap. `agent.py`.
   Done when: a scripted model that fails repeatedly stops early, with a test.
   Done 2026-10-19: Codex `61181b1` + Beacon-17 `f21331f` (red test runs don't count).
2. [x] **PagerDuty escalation (#2).** A Broadcast from `phil`/`phone` with no reply in
   N minutes escalates through the roster, then the phone topic ("nobody picked up").
   New `src/megazword/escalate_watch.py` + tests + a CLI hook.
   Done when: a fake clock shows primary -> secondary -> phone.
   Implemented: `megazword room escalate [--room hive]` runs one pass. Unanswered
   calls ping roster seats at 5/10 minutes, then the phone at 15. No scheduler.
   Set `[room] ntfy_pc_topic` and `ntfy_phone_topic` in config.toml (or environment
   `MEGAZWORD_NTFY_PC_TOPIC` / `MEGAZWORD_NTFY_PHONE_TOPIC`; Worker-style
   `NTFY_PC_TOPIC` / `NTFY_PHONE_TOPIC` also work). No topics means no sends.
   Replies start with a Word-NN designation or reference `hive:ID`, `#ID`,
   `call ID` or `message ID`. State is saved beside the room wait bookmarks.
   Per-seat paging: steps 1-2 target `megazword-hive-seat-<seat>`; a seat listens on
   `shared,megazword-hive-seat-<designation>` (one ntfy subscription, comma-separated).
3. [x] **Tool-result cache (#10).** `read_file` / `search_files` results cached by
   path+mtime per job and reused instead of re-read. `agent.py`.
   Done when: a repeated read returns cached text and `tool_chars` stays flat.
   Done 2026-10-19 (Fathom-19, claimed 08:33): an identical read on an unchanged file
   (mtime+size) or a search with no edit since costs a one-line note while the earlier
   result is still whole in the history, else the cached text; no disk re-read.
4. [x] **`megazword job cost ID` (#13).** One command prints tokens and steps per model
   for a saved job, from `log.jsonl`. New module + tests.
   Done 2026-10-19 by Quill-21: `src/megazword/job_cost.py` + `megazword job cost ID`.
   Reads the run log's `project=<job id>` lines, totals steps (`requests`) and
   `est_tokens` per backend, and prints the estimate's definition rather than
   letting it pass as billed tokens. 7 tests; suite 1604.
5. [x] **Repo map (#17).** Regex-based ranked map of key symbols offered to models
   instead of file dumps. Module by Juniper-16 (`megazword map`); prompt hook by
   Lumen-20 (`81b4f2d`): 6k chars, built once per job, focused by task words, and
   cache-stable in `agent.py`.
6. [x] **RimWorld priority grid (#14).** Seats x work types in one table Phil can edit.
   Done 2026-10-19: grid added to `docs/HIVE-ROSTER.md`.
7. [x] **Powerwall reserve (#8).** `megazword usage` appends each metered AI's
   reserve and spendable percentage, or `AT RESERVE: hold heavy work`.
   Display only; routing is unchanged. Default 20%; override in
   `~/.megazword/config.toml` with `[usage.reserve]` and e.g. `claude = 30`
   (clamped to 0–100). Unknown meters get no suffix.
8. [ ] **Andon (#7).** `megazword andon on|off` pauses jobs for everyone (a flag the
   agent loop checks before each step).
9. [x] **Spot warning (#9).** `megazword spot` prints any plan at or below 25% left,
   marks 20% as STOP, ignores unknown buckets, and writes
   `~/.megazword/spot-handoff.json`. Done 2026-10-19 (Lumen-20), 5 tests.
10. [x] **WIP cap (#7b).** At most one active claim per seat in the room.
    `room claims` lists active claims and item conflicts; `room say` refuses a
    second claim or another seat's item unless `--force` is used. A failed room
    read permits posting. Claims use text designations, never lane tags.
    Ledger fixed 2026-10-19 (Lumen-20, `a300cf9`): newest claim wins (a dead first
    claim no longer blocks), release words widened (merged/shipped/complete), and
    `MEGAZWORD_CLAIM_STALE_MINUTES` gives a night shift a shorter leash.
11. [x] **Seat renames its own tab (#18).** A bot runs under a hidden console, so it
   cannot see or set the tab Phil is looking at, and Command Code keeps re-asserting
   its own title over any one-shot change.
   Implemented 2026-10-19 (Cinder-21): `megazword tab <designation>` walks up to the
   shell Windows Terminal hosts for this tab, attaches to that console, and sets the
   title; a small keeper re-applies it while the tab lives (`megazword tab --stop`
   ends it). New `src/megazword/tab_title.py` + tests.
   Limits: a tab started with `--suppressApplicationTitle` (claude/codex/grok/gemini
   via `hive_up.ps1`) ignores application titles, so the rename will not show there.

## Later (needs data or a stable process)

- **LLM router (#15):** needs scoreboard volume first.
- **BOINC quorum (#16):** only for high-risk outputs; doubles spend.
- **Flight strips / KDS boards (#4, #6):** UI on a process that is not stable yet.

## Progress

- 2026-10-19 ~01:00: roadmap written; conductor loop pointed at it.
- 2026-10-19 01:05: lane attribution fixed — a `lumen-20` lane was added to the
  Worker without rotating any key, and `RemoteRoom` now prefers
  `HIVE_ROOM_KEY_<SEAT>` over the shared token. Conductor posts read `lumen-20`.
  `megazword announce` now pings the PC ntfy topic and `room_wait` treats
  `ANNOUNCE:` as actionable, so an announcement actually wakes seats.
- 2026-10-19 01:35: reconciled the shared checkout. Recovered Quill-21's business
  lane (`5721f26`: `BUSINESS-MODEL.md`, `LANDING-PAGE.md`) and Gauge-18's
  `REPO-MAP.md`; landed with `REVENUE-OS.md` and per-seat ntfy paging at `606eb91`.
  Added lanes `quill-21` and `cinder-21` without rotating keys.
