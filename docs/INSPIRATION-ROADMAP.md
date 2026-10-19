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
3. [ ] **Tool-result cache (#10).** `read_file` / `search_files` results cached by
   path+mtime per job and reused instead of re-read. `agent.py`.
   Done when: a repeated read returns cached text and `tool_chars` stays flat.
4. [ ] **`megazword job cost ID` (#13).** One command prints tokens and steps per model
   for a saved job, from `log.jsonl`. New module + tests.
5. [ ] **Repo map (#17).** Regex-based ranked map of key symbols (~1-2k tokens) offered
   to models instead of file dumps. New `src/megazword/repo_map.py` + tests + one
   prompt hook.
   Module done (Juniper-16, 2026-10-19): `megazword map [focus...] [--root] [--chars]`,
   ~5k chars for this repo. Prompt hook still to do, after #1 lands in `agent.py`.
6. [x] **RimWorld priority grid (#14).** Seats x work types in one table Phil can edit.
   Done 2026-10-19: grid added to `docs/HIVE-ROSTER.md`.
7. [ ] **Powerwall reserve (#8).** Show the 20% floor per AI in `megazword usage`.
8. [ ] **Andon (#7).** `megazword andon on|off` pauses jobs for everyone (a flag the
   agent loop checks before each step).
9. [ ] **Spot warning (#9).** A seat near 25% writes a checkpoint note and hands off.
10. [ ] **WIP cap (#7b).** At most one active claim per seat in the room.

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
