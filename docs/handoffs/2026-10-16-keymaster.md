# Keymaster, small version (ROADMAP item 2)

**Status:** done by Alder-16 (Codex), 2026-10-16; source e285f0a, added prompt regression ca787e7. Written by Juniper-16 (Claude Code), 2026-10-16.
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


## Report — Alder-16, 2026-10-16

Implemented Keymaster in `keys.py` with a small `credential_store.py` ctypes
wrapper. Environment-first lookup now reaches free backends and doctor. Vault
values are covered by prompt, response, error and export scrubbing. Metadata
checks are deduplicated per provider, reject redirects, and make no inference
calls. OpenRouter uses authenticated `/key`; Gemini and Cloudflare use their
native metadata endpoints. Unsupported metadata endpoints yield `no answer`;
`ok` is not a free-quota or inference-access guarantee.

Move copies user-environment values (including registry values not inherited by
an older shell), verifies each write, and leaves environment values untouched.
Process/user conflicts are skipped. Optional cleanup uses exact PowerShell
SetEnvironmentVariable lines rather than unreliable `setx NAME ""` deletion.
Phil runs the real migration himself. No real credential writes were performed.

Free coding: Tencent GLM-5.3 Flash timed out; Groq Qwen hit the 10-step cap with
an unusable draft. Groq GPT-OSS 120B through Mega Zword produced the accepted
wrapper draft; Alder corrected platform detection, pointer assignment, input
validation and cleanup/error handling, then integrated and tested it. Gemini
API reviewed all source changes with no findings; Groq's review returned an
invalid response. Review's 24k cap excluded the two new test files.

Validation: full suite 1,353 passed in 209.44s; final Keymaster prompt regression
suite 17 passed; ctypes fake tests cover read/write/delete, missing/errors,
UTF-8 byte limits, zeroing, and prototypes. No test writes to Credential Manager
or makes provider calls. `git diff --check` passed. Testlog's concurrent runner
fix was retained by clean rebase; no edits to routing/ledger/review/night.

Installed wheel into canonical app venv and system Python311. Both installed
CLI entrypoints recognize `keys --help`; all 63 package/UI files match source
content (normalizing line endings; keys.py changed LF/CRLF on rebase). Existing
app processes were not restarted. Build required standard isolated setuptools
build because both installed build environments have older setuptools.

Next for Phil: `megazword keys` checks providers; `megazword keys move` performs
the one-time migration. Restart existing shells/apps after optional environment
cleanup. Existing GUI processes need reopening to load updated package code.
Routine source stays on local Gitea; no GitHub source mirror.

Implementation references: [Microsoft CREDENTIALW](https://learn.microsoft.com/en-us/windows/win32/api/wincred/ns-wincred-credentialw),
[CredReadW](https://learn.microsoft.com/windows/win32/api/wincred/nf-wincred-credreadw),
[OpenRouter key check](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key),
[Gemini models](https://ai.google.dev/api/models),
[Cloudflare model search](https://developers.cloudflare.com/api/resources/ai/subresources/models/methods/list/).
