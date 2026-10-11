# Handoff: Claude, light lead for Beta 2

- **For:** any Claude Code session on Phil's PC (Kestrel's seat)
- **Status:** open
- **Written by:** Tally-11 (Claude Code), 2026-10-11
- **Why light:** Claude has the tightest usage (59% of the 5-hour window, 31% of the week, at assignment).
  Keep Claude for judgment work.
- **Items:** reviews and merges; B2 (SPEC.md section R)

## The job
- Review and merge finished Beta 2 branches (tests + smoke must pass). Keep STATUS.md lanes true and
  reassign when someone runs low. Check `megazword usage` first.
- **B2 Lessons and summaries**, after B1 lands. Save 3-5 lessons per room session to the primary project's
  memory, write summary files to `~/.megazword/rooms/summaries/`, and add `megazword room post-summary`
  (it posts to Q with gh, or prints).
- Phil still has to: merge workshop PR #49, and decide on the "MegaZword usage board" scheduled task
  (the command is in Tally-11's chat; `scripts/publish_usage.py`).

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
