# Free public-URL tool: scheduled run and recovery

- **For:** Testlog-14 (Codex), recovery of Phil's free public-URL tool task.
- **Status:** the 2026-10-15 23:43 run failed; recovered in the current worktree and awaiting final local-Gitea push.
- **Observed result:** Tencent Kimi K2.7 Code ran for 259.8 seconds, hit the agent's 60-step cap, returned no usable answer, and left no tracked diff. The local Mega Zword `[agent]` config sets `max_steps = 60` and `wall_timeout = 1800`; the earlier handoff's 30-step / 10-minute values described defaults and were stale. The run hit its step cap before the outer 15-minute launcher limit.
- **Validation:** focused agent/fetch tests: 108 passed. Full suite: 1303 passed in 177.20s on the final source. Morning runner dry-run and `git diff --check` pass. No live public URL request has been made.
- **Done when:** finish final review, record the local-Gitea commit hash here and in `docs/STATUS.md`, then push the reviewed result to local Gitea `origin`. Never commit `CODEX_JOB.md` or push routine work to GitHub.

## Why and scope

Phil asked for Mega Zword's API coding bot to have practical tools beyond source-file access. The first bounded capability is reading a user-specified public HTTPS URL, with SSRF protections and response limits. Do not add shell access, authenticated browser/cloud-console access, billing/API-key operations, or secret access in this run.

## Scheduled runner

- Task Scheduler task: `MegaZword-FreeTools-Testlog14` (one time, 11:43 PM local; hidden PowerShell, current user, no automatic retry).
- Tracked launcher: `scripts/continue_free_tools.ps1`.
- Runner: Tencent `tencent-kimi-k2.7-code`, forced with Mega Zword `--free-only`; no paid fallback. The API credential is read from the existing local Mega Zword configuration and is never written to the handoff or logs intentionally.
- Bound: one model run; Mega Zword's agent has a 30-tool-step / 10-minute wall limit; launcher stops after 15 minutes. The job does not commit or push.
- Durable status: `%LOCALAPPDATA%\MegaZword\FreeToolsContinuation\2026-10-15-2343\status.json`.
- Output log: `%LOCALAPPDATA%\MegaZword\FreeToolsContinuation\2026-10-15-2343\run.log`.
- Cancel marker: create an empty `STOP` file in that same directory. It is checked during the run; the launcher itself also exits if it starts after 12:13 AM.

Check with:

```powershell
Get-Content "$env:LOCALAPPDATA\MegaZword\FreeToolsContinuation\2026-10-15-2343\status.json"
Get-Content "$env:LOCALAPPDATA\MegaZword\FreeToolsContinuation\2026-10-15-2343\run.log"
```

The scheduled run did not complete; its status is `failed` and its log records the agent step-cap error. Testlog-14 then implemented the capability directly after the free model run failed. One read-only DeepSeek review attempt also produced no output after roughly 3.5 minutes and was canceled; the implementation was completed from direct source inspection. The 5:00 AM morning runner is instructed to inspect the recovered source and tests, avoid duplicating the fetch tool, and proceed to a source-grounded audit step.
