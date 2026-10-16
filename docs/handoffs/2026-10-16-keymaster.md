# Keymaster, small version (ROADMAP item 2)

**Status:** taken by Alder-16 (Codex), 2026-10-16. Written by Juniper-16 (Claude Code), 2026-10-16.
**Claim it:** pick a designation, put it on the Active line of docs/STATUS.md, commit and push, work in your own worktree (`git worktree add %USERPROFILE%\mz-seats\<name> -B seat/<name> origin/main`). Pushes go to local Gitea `origin` only.

## Why
Mega Zword keeps adding free sources, and each one is another API key. Today they sit in
plain Windows user environment variables (setx), readable by any program running as Phil.
Phil wants one place that stores them safely and tells him which ones work. Hard rule:
**no AI model ever sees a key value**, not in prompts, logs, output or test fixtures.

## What to build
1. `src/megazword/keys.py` using Windows Credential Manager through `ctypes`
   (advapi32 `CredWriteW` / `CredReadW` / `CredDeleteW`, `CRED_TYPE_GENERIC`, target
   `megazword:<ENV_NAME>`, persist `CRED_PERSIST_LOCAL_MACHINE`). No new dependency.
   On non-Windows, the store is unavailable and everything falls back to env vars.
2. Key lookup: one function `get_key(env_name)` = environment variable first, then the
   Credential Manager entry. Use it everywhere a key is read today: `free_apis.py`
   (`OpenAICompatibleBackend.available()` around line 273 and the request around line 308,
   plus `extra_env` like `CLOUDFLARE_ACCOUNT_ID`) and anything else that reads `*_API_KEY` /
   `*_TOKEN` from `os.environ` (grep for it). Keep the existing secret scrubbing.
3. `megazword keys` (show): one row per key name in `free_apis.FREE_KEYS` plus
   `CLOUDFLARE_ACCOUNT_ID`: where it lives (env / vault / missing) and a check result from
   one free, tiny call per provider (prefer listing models, e.g. `GET /models`; reuse
   `free_test.py` where it fits). Show `ok`, `rejected (401/403)`, `rate limited`, `no answer`.
   Never print any part of a value; not even the last 4 characters.
4. `megazword keys move`: copy every present user-env key into Credential Manager, read it
   back to verify, then print the exact `setx NAME ""`-style lines Phil can run to clear
   the env copies. Do not delete env vars automatically (Phil's call).
5. Add `keys` to `COMMAND_GROUPS` in cli.py (Set up section); keep help lines short (one line).
6. Tests with fakes only: monkeypatch the ctypes layer; no real Credential Manager writes,
   no network. Include a test that no output line contains a fake key value.
7. One short GUIDE.md section: what it does, the two commands, the rule that AIs never see keys.

## Done when
`megazword keys` and `megazword keys move` work with fakes in tests, the full suite passes,
free backends still find keys from env (nothing breaks for Phil before he moves them), and
ROADMAP item 2 is ticked with date, who and commit. Update STATUS, clear your Active line,
publish a `megazword brief report` card.

## Don't
- Don't run `keys move` on Phil's real keys yourself, or touch his env vars. He runs it once.
- Don't send keys to any model, log, Q comment or GitHub.
- Don't edit `routing.py`, `ledger.py`, `review.py`, `night.py` (Juniper-16 is working on
  the heartbeat in night.py and a new heartbeat module).
