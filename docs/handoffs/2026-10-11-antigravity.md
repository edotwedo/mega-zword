# Handoff: Antigravity pool, Beta 2 room engine (B1)

- **For:** an Antigravity CLI (`agy`) session on Phil's PC, using its **Claude or GPT** models. That pool
  is separate from Phil's Claude and ChatGPT plans, and it has a full week unused.
- **Status:** done 2026-10-11 (Atlas-11 / Antigravity on Phil's PC)
- **Written by:** Tally-11 (Claude Code), 2026-10-11
- **How Phil starts it:** in `C:\Users\mrmar\mega-zword` run `agy`, pick a Claude or GPT model, and say
  "read docs/handoffs/2026-10-11-antigravity.md and do it". Pick your own designation.
- **Items:** B1 (SPEC.md section R)

## The job
Build `src/megazword/room.py`: the Hive room, a lightweight group chat for the bots.
- The room file is `~/.megazword/rooms/<room>.jsonl` (time, author, text, mentions).
- Turn loop: an `@claude` / `@codex` / `@grok` / `@gemini` mention makes that bot reply next. Phil's messages
  always go first. The prime directive prompt: work the primary project (`[room] primary`), use spare usage.
- Turn cap (default 12). Stop early when every AI is out or over pace. One AI talks at a time.
- Lean, read-only one-shots only (never `--edit`), replies capped at about 80 words.
- **Token budget (Phil, 2026-10-12), part of B1, not a later fix:** state card instead of the full room,
  rolling summary plus the last 4 messages, wake only the mentioned AI, reuse CLI sessions where supported
  (fall back to one-shots), and log prompt size per turn. Details: SPEC.md section R, "Token budget".
- CLI: `megazword room start|stop|say|show`. Tests use the fake CLIs. Claude adds lessons and summaries
  later (B2), and Codex builds the screen for it (B4).

## Start here (same for every lane)
1. Read `AGENTS.md`, then `docs/STATUS.md` ("Beta 2 lanes") and `docs/SPEC.md` ("Beta 2").
2. Run `megazword usage` (Phil's rule: check usage before and after each step; say so if you pass 80%).
3. Put your designation next to the item in STATUS.md, commit, push. Work on your own branch
   (`<you>/<item>`), for example `grok/b3-tabs`.
4. Tests must pass before you push: `.venv\Scripts\python -m pytest -q` and
   `.venv\Scripts\python scripts\smoke.py`. Tests never call a real AI (fakes only; see
   `tests/conftest.py` and `scripts/fake_cli/`).
5. When an item is done: push, mark it done in STATUS.md, and post one line in Q
   (workshop PR #33) with the branch name. A Claude lead merges.
6. Never commit secrets. Ask Phil only what is truly his call.

## Report (Atlas-11 / Antigravity, 2026-10-11)
- Built `src/megazword/room.py`: Hive room JSONL storage (`~/.megazword/rooms/<room>.jsonl`), @mentions loop, Phil-first priority rule, prime directive prompt, turn cap, early stop when out/over-pace, lean read-only one-shots, and ~80-word replies.
- Implemented full token-budget optimizations:
  1. Concise state card (<300 words: primary project, in progress, last 3 decisions, schedule).
  2. Rolling summary + last 4 messages, condensed after every 6 turns.
  3. Wakes only the needed AI (burn order fallback when no mention).
  4. Session reuse where CLI supports it with one-shot fallback.
  5. Prompt size (chars and estimated tokens) logged per turn to `log.jsonl` and in room records.
- Added CLI commands: `megazword room start|stop|say|show|post-summary`.
- Tests: 541 passed, smoke 31/31 passed.
- Branch `agy/b1-room` pushed and ready for lead review / merge.

