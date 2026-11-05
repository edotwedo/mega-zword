# Status

**Active: RobinTHood Production Launch & Obsidian Vault Integration (2026-11-05).**
- **Top Priority:** Closed testing for 14-day Play Store policy underway on `track001` with 102 vetted testers uploaded (`com.edotwedo.robinthood`).
- **Google Play:** Closed testing track `track001` updated to versionCode 25 (`v0.8.6`) with R8 minification, DEX optimization, and resource shrinking active; status verified `completed`. Runner workspace on Donna's PC migrated to C: NVMe SSD.
- **Store Listings & App Store Prep:** Lane 4 completed in PR #31 (`STORE-LISTINGS-ALL-LANGUAGES.md` with Play Store listings in 8 languages, App Store draft, Apple privacy nutrition labels).
- **Privacy & Obsidian Vault:** Bi-directional wire-level PII tokenization, persistent `_vault_secrets.json` and frontmatter entity shielding, air-gapped Ollama lockdown, and LAN Ollama auto-discovery landed on `claude/android-rebuild`. 65/65 unit tests pass.
- **Web & Landing Page:** Deployed live to Cloudflare Pages (`robinthood.com` and `www.robinthood.com` HTTP 200) with honest privacy disclosures.
- **iOS Track:** Release workflow staged in `.github/workflows/build.yml` (`ios-release` job) and `docs/IOS-RELEASE.md` ready for Apple Developer credentials.
- **Handoff Detail:** `robinhood-mobile/HANDOFF.md` and `docs/handoffs/2026-11-02-robinthood-launch.md`.

## Previous Standing State
Nock-21 (Grok), 2026-10-25: F1b is on main `6d3b278` and live as Worker `c612ea4c`. No open task.

M2 file leases: Briar-20 implementation is on `seat/briar-20`, awaiting independent
review/integration. Task IDs and branches share 30-minute renewable leases across
worktrees; the tracked pre-push gate checks conflicting changes before/after tests.
Focused temp-repo tests include actual refused/expired-lease pushes. `docs/TASKS.md`
documents use and limits: this is a local push gate, not an OS editor lock.

**Live file. Hard cap 8 KB, enforced by `tests/test_status_size.py`.** History before 2026-10-22 is in
`docs/STATUS-ARCHIVE.md`, moved there verbatim. Reason, from Forge-22's proposal carried 5-0 as ballot
P2/A1: this file grew to 112 KB and became a changelog, and every seat paid ~28k tokens to read it at
startup on every session.

## Where the system stands (2026-10-22)

**Rules.** `docs/SYSTEM-DRAFT.md`, approved by ballot P1 (5-0) with three caveats folded in: locks
carry an expiry and hot files are never locked, M3 accepts any non-author reviewer, and the supervisor
makes no idle model calls. M8: no rule changes without a ballot, enforced by `megazword rules check`,
which hashes the file as committed on `origin/main` so a stale worktree cannot fail the gate.

**Ballots.** P1 rules carried. P2 startup cost carried 5-0 and both parts are built: A1 split this
file (capped by `tests/test_status_size.py`), A2 generates `docs/MEMORY-INDEX.md` - with the condition
three seats insisted on, that the gate itself rebuild it, because a stale index is worse than none.
P3 integrator amendments (B1 named deputy for M1, B2 30-minute renewable lock) carried 3-0 and are in
the rules. P4 adopted `docs/PROPOSAL-beat-hermes.md`. P6 carried 3-0: a second-vendor review is
required for code only; docs, config and data are exempt (rescopes P5, which is superseded).

**Live mechanisms.** `vote` (new/cast/tally), `rules` (hash gate), `seat` (status/watch/retire/
replace), `wake` (scheduled listener types into the conductor's tab within a minute of a Phil post),
room `kinds`, `doctor` room health, `startup` (one bounded 10s read), `index` (generated memory
index; the pre-push gate regenerates it and refuses a stale one), Discord mirror, per-seat room
tokens, fixed Worker claim guard, `guard` (monthly pace guard: projects each window's burn rate,
throttles a plan running ahead of its monthly clock, posts one line when the state changes).
Still `[to build]`: M1 merge queue, M2 file locks, M3 machine-checked review, M6 command grammar.

**Team.** Forge-22 (Lead Conductor / Owner, Phil 2026-10-23), Cinder-21 (cmdc, rotated), Harbor022, Briar-20/22, Nock-21.
Forge-22 runs in its real conversation `3bc1d242`, but Windows Terminal is elevated, so SendKeys
cannot reach it - Phil can type there, the supervisor cannot.

## Active tracks (Phil, 2026-10-23)

- **Forge-22a:** Upgrading RobinCode (`C:\Users\mrmar\robincode`). Fully approved by Phil.
- **Cinder-21:** Sales pipelines via Spanda (`C:\Users\mrmar\interference`) selling Spanda + RobinCode. Fully approved by Phil.
- **Forge-22 (Lead Conductor):** Overseeing Hive execution, Hermes competitor work, Mega Zword tooling.

## Next, in order

1. M1, M2, M3, M6 - the choke points, in that order. M2 is built and accepted on `seat/briar-20`
   (`ee42241`); it needs a rebase onto main before it lands.
2. The Hermes execution plan - `docs/PLAN-hermes-execution.md`, Wave 1 (F1 + M2) first.
3. Convene - `docs/FEATURES.md`: agents argue assigned stances, structured on the wire, English on
   screen.

## Standing facts

- The suite is the gate. The winpty flake in `tests/test_terminal_input.py` passes alone, so check it
  alone before blaming a change.
- Usage floor: five-hour window, 10% remaining means hand off; weekly drains to 5% then hard stop.
- Usage doctrine (Phil, 2026-10-23): ALWAYS use free options where available unless nearing end of weekly reset with unused allowance ("at that point go nuts").
- Heartbeat cadence: every seat maintains an active 10-minute Hive check to resolve questions and avoid conflicts.
- Room text is communication; only Phil's lanes carry authority. Verify a session before routing work
  to it - a saved name is not evidence of a live connection.
