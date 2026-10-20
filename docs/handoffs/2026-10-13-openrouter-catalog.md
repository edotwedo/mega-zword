# OpenRouter catalog and free coding failover

Reed-13, Codex worker for Sorrel-12 / Phil, 2026-10-13.
Worktree: `C:\Users\mrmar\mz-seats\codex-catalog`. Changes are uncommitted.
Phil explicitly requested skipping startup/coordination and forbade commits.

## Delivered

- Named `kimi`, `deepseek`, `qwen-coder` OpenRouter backends in normal and edit runs.
  All use `OPENROUTER_API_KEY`. Override `[free.<name>] model` in config.toml.
  Defaults: `moonshotai/kimi-k2.6:free`, `deepseek/deepseek-chat-v3.1:free`,
  `qwen/qwen3-coder:free`. GUIDE links current catalog pages and the paid Kimi
  latest alias; check exact IDs/prices before live use.
- Training policies vary by serving endpoint; unknown counts as True for the
  named backends. Existing prompt/file-result scrubbing applies before handoff.
  Aliases share OpenRouter's provider pacing lock/quota.
- `[agent] failover_order` defaults to kimi, qwen-coder, deepseek, groq,
  gemini-api, cloudflare, mistral, ollama. The explicitly selected backend goes
  first; skip missing keys, unavailable servers and marked-out fallback names.
  `[]` disables switching. No automatic paid-model upgrade.
- API failures and timeouts switch inside the same coding loop, preserving the
  task, observations, files, original diff, test results and quality checks.
  Shared wall/step limits still apply. Tool-format rejection first tries JSON.
  Reviewer and test failures retain their existing behavior.
- Run logs include switch history, final backend and per-backend request counts.
  Terminal reports switches and the backend that actually finishes.
- GUIDE includes Google sign-in, Keys / Create Key, `setx OPENROUTER_API_KEY`
  and opening a new terminal. Added fake-only regression tests.

## Validation

Final focused command using Phil's shared interpreter:

```powershell
C:\Users\mrmar\mega-zword\.venv\Scripts\python.exe -m pytest -q tests/test_catalog_failover.py tests/test_agent.py tests/test_agent_pacing.py tests/test_free_apis.py
```

**180 passed**, including final cap/local-fallback tests and logging refinements.
No live model requests. `git diff --check` passed.

The requested full command was run before the final three extra regression tests
and small logging/refactoring changes: **1000 passed, 5 failed, 9 setup errors**.
Cannot certify the full suite green in this sandbox:

- `test_codex_live.py::test_silent_app_server_times_out_and_falls_back`
- `test_codex_review.py::test_add_user_path_keeps_vars_duplicates_and_is_idempotent`
- `test_dashboard.py::test_real_job_cancel_kills_process`
- `test_dashboard.py::test_cancel_stops_backend_child_too`
- `test_timeouts.py::test_dashboard_cancel_kills_the_ai_underneath`
- Nine Night Shift fixture errors during local bare-repo cloning.

Independent reproduction: taskkill on our own temporary Python process returned
`ERROR: Access denied`; Git clone failed with `couldn't create signal pipe,
Win32 error 5`. The registry test produced no expected RAW result. These paths
are unchanged by this task; no tests were skipped or weakened to claim green.

## Next step

Sorrel-12: review the uncommitted diff, rerun the full suite outside this sandbox:

```powershell
C:\Users\mrmar\mega-zword\.venv\Scripts\python.exe -m pytest -q
```

Then commit/publish when authorized. No keys, live configuration, installation,
coordination posts or shared-main files were changed by this worker.
