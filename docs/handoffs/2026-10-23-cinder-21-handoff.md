# Handoff: Cinder-21 -> the next cmdc conductor, 2026-10-23

## 0. READ THIS FIRST - do not destroy your context window

Two conductors have now retired on context-full. The last one (me) burned a large part of its
window **in the first five minutes**. Do not repeat it.

- Read exactly two files to get up to speed: `docs/STATUS.md` (2.6 kB) and `docs/MEMORY-INDEX.md`.
  Open anything else only when a trigger in the index matches the job in front of you.
- **Never** run `git branch -r` unfiltered - it is ~250 lines and tells you nothing.
- **Never** read a whole file to answer a question about one function. Use offset/limit.
- Pipe bulk output: `... | Select-Object -Last 20`. If you need to scan a lot, hand it to a
  subagent and read the summary.
- This window is a shared resource. Running out is not a personal inconvenience; it is a second
  emergency for the team.

## 1. Start here

1. `megazword rules check` - must print OK (approved by P6). If not, stop and read the rules gate.
   On Windows there is a known bug: `rules approve` records the CRLF working-tree hash while
   `check` compares the LF `git show` hash, so `approve` can never satisfy `check`. Fix recorded
   as work; workaround is to `git checkout` the file and approve when it is LF on disk.
2. `megazword guard status` - the usage governor's last reading.
3. `megazword room show --room hive -n 30` for the room. **Never `room.read_messages`** for this:
   it reads the local cache.

## 2. Where the system stands (main = 50d6fcd, origin/main in sync)

- **origin is the live remote** (local Gitea, `127.0.0.1:3000`). The GitHub remote is ~237 commits
  behind; ignore it.
- Land-gate: `git push` runs the full suite (~4-5 min, currently ~2018 passed / 1 skipped) and
  regenerates `docs/MEMORY-INDEX.md`, refusing the push if it was stale. Delete-only pushes skip it.
- **`megazword guard`**: reads every plan's windows on a 30-min scheduled task (`MegaZword-Guard`,
  own STOP file at `~/.megazword/guard/STOP`), projects the burn rate, marks a plan `throttle`
  when its monthly window runs ahead of its own clock, and posts one room line only on a whole-day
  change. It protects the plan you are running on - heed it.
- **cmdc usage now comes from the vendor API**, not the `/usage` panel scrape: `read_api()` in
  `src/megazword/cmdc_quota.py` calls `api.commandcode.ai/alpha/billing/credits` (fiveHour/weekly),
  `/alpha/usage/summary` (monthly), `/alpha/billing/subscriptions` (planId + renewal) with the
  `apiKey` from `~/.commandcode/auth.json`. Fallback: panel scrape, then transcripts. Off under
  `MEGAZWORD_NO_CMDC_API=1`. Do not log the key.
- Landed tonight: the rules-gate unblock (P6 approved), `megazword guard` (+ a noise fix), Briar-20's
  M2 file leases, the cmdc API reader, and `[phil] authors` config.

## 3. Open work (Wave 1 of `docs/PLAN-hermes-execution.md`)

| Item | State |
| --- | --- |
| F1a outbox cannot jam | **landed** |
| M2 file leases | **landed** |
| F1b Worker claim guard | Nock-21 - status unconfirmed |
| **F1c reads cannot go stale silently** | **IN FLIGHT** - a subagent is on branch `cinder/f1c-stale-reads`; check that branch, run the suite, review, land |
| F1d the listener cannot lie | open (was handed to Nock-21) |
| F1e per-seat room keys, F1f single-flight meter | open (Harbor022) |
| F2 heartbeat + watchdog + daily probe | open, **unowned** |

Waves 2-5 (M1 merge queue, M6 grammar, F3 status page, A1-A3, C/D/E items, benchmarks, launch) are
**not started**.

## 4. Traps that cost real time

- `tests/test_terminal_input.py` has a known winpty flake - run it alone before blaming a change.
- **Never edit `docs/SYSTEM-DRAFT.md` without a ballot**; it is hash-locked (M8). Rule changes go
  through `megazword vote` then `megazword rules approve <ballot>`.
- **The npm install of `command-code` is half-swapped**: `node_modules/command-code/dist/` holds
  only `bundled/`; the real bundle sits un-renamed in `node_modules/.command-code-ANXWRD9O/`, and
  there is no `cmdc.cmd` shim. Repair with `npm i -g command-code`. The API meter does not depend
  on it; the panel-scrape fallback does.
- A room post does **not** wake a seat. Delivery is typing into the window or an ntfy page; Windows
  Terminal runs elevated, so the supervisor cannot SendKeys into it.
- Windows `core.autocrlf=true`: markdown files carry CRLF in the working tree.

## 5. How Phil is operating right now

- He wants **momentum**, and he is explicitly tired of **stoppages over approval**. His asks are
  his asks - act on them. Do not demand doctrinal proof from him.
- Relays from *his own instances* are him, not "a report to verify". `[phil] authors` in
  `config.toml` is now the single place to add an instance of his; wake, room wait and escalation
  all read it. (Known tension, accepted for now: this also loosens the check that caught a bot
  relaying a directive on 2026-10-19. Hardening is deferred, not forgotten.)
- Use the team and the free sources; do not do every build yourself. The conductor integrates.
- Delegation, not essays: one line per landing, and post nothing when nothing changed.

## 6. Facts

- `docs/STATUS.md` is capped at 8 kB by `tests/test_status_size.py`.
- Suite runner: `.venv\Scripts\python.exe -m pytest -q`. Shell is PowerShell (`Select-Object`, not
  `head`).
- `MEGAZWORD_CMDC_METER`/`MEGAZWORD_NO_CMDC_METER` disable cmdc metering (tests set it).
