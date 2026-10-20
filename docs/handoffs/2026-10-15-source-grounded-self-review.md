# Mega Zword: Source-Grounded Self-Review

Owner: Testlog-14 (Codex). Phil requested diagnosis and repair after the app
returned a generic plan instead of inspecting its own code. He selected this
update for a GitHub save point and requested an official name. His concurrent
six-model Tencent integration62120e6 is preserved in this branch.

## Observed failure

Dashboard j1 / last_run.json sent only the559-character user prompt to Tencent
GLM-5.3. It had no source or file tools; its generic response explicitly denied
access to Mega Zword code and then suggested an unverified generic architecture.
The model call completed, but pythonw printed under cp1252 and raised a
UnicodeEncodeError on an arrow. The model run was logged successful while the
dashboard job failed. The user's no-paid instruction existed only in prompt
text; subscription backends remained eligible fallbacks, although none ran.

## Resulting behavior

- Dashboard code-inspection requests automatically select the existing agent
  loop in read-only mode. The editing checkbox remains required for edits.
- Mega Zword self-review reads the installed package's actual source; an older
  shared checkout is not silently substituted. Other reviews use the current
  work folder. CLI: `megazword run --review --review-root PATH "review code"`.
- Only list_files, read_file and finish are advertised and enforced. Writes,
  replacements, commands and tests are refused. Successful reads supply numbered
  lines; finish requires actual file access and a citation. Generated directories
  are omitted from file maps. No whole-repository upload or web tool is added.
- Reviews and free-bot coding use free-only routing. Explicit no-paid prompts also
  set that policy. Subscription CLI fallbacks and paid OpenRouter overrides are
  excluded, including on Retry. Mode/root/policy are saved; legacy prompt-only
  code reviews are upgraded to read-only review when retried.
- Provider account free quotas and billing settings still govern API charges;
  this is a routing restriction, not an account billing guarantee. No payment or
  postpaid setting was changed. All six configured Tencent identities pass the
  policy; incoming62120e6 was fast-forwarded before combined validation.
- Dashboard subprocess input/output is UTF-8. Read-only review has visible mode,
  live tool activity and existing pause/instruction controls.

## Evidence and deployment

The original full suite passed1276 tests. A real bounded Tencent GLM-5.3-Flash
trial probe read actual routing.py and finished with line-cited findings in TWO
requests; no edits, tests, browsing or paid backend fallback. The independent
review scope was routing.py only. Artifact build/self-review-live.json records
the answer, file reads, backend and request count. This proves source access,
not a comprehensive review of every module.

Final policy/CLI checks127 passed, including legacy Retry. Combined full-suite
with six Tencent models:1279 passed in181.90s,115 existing deprecation warnings.
Wheel/source byte comparison is clean. Source build ce501da is installed in both dashboard venv and system Python311; installed source bytes match. Desktop/Start Menu shortcuts identify ce501da, with backups retained. GitHub branch codex/source-grounded-self-review is published; this handoff accompanies the main advance on local Gitea and GitHub. Active claim released for the waiting worker. Installed app must be
closed/reopened by Phil to load new in-memory code. Do not stop live jobs or
touch terminal chats/desktops/focus. Prior guarded camera helper and worker UI
remain intact. No Windows restart needed. CODEX_JOB.md remains untracked.
