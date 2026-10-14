# Night Shift repair

Lantern-13 (Codex), explicitly assigned by Phil on 2026-10-14.
Branch: `codex/night-repair-2026-10-14`.

Observed on this PC: installed main was `4819543`, 26 commits behind
`26b08b4`. Scheduled task uses its editable-install Python, so Quill's merged
PR 48 (wall-timeout assertion) and PR 49 (free-first eligibility/coding loop)
were not loaded. Installed main was fast-forwarded without changing the
untracked `scripts/setup-phil.ps1`. Task remains daily at 01:00, pythonw.

The 07:35 summary reported seven failed jobs and one skipped job; repeated
full-suite failures burned Codex to 91% of its five-hour window. No previous
job is rerun or declared successful by this repair.

Additional repair:
- Run the detected repository suite on the clean base before any model call,
  once per repo/base revision per run. Cache both success and failure.
- Broken baselines skip model work and remain queued. Other repos can continue.
  A new base revision is checked again; explicit job acceptance commands are
  deliberately excluded from baseline detection.
- Save scrubbed baseline/worker failure output under night/test-results.
- Keep configured free model names, pacing and agent settings; apply paid
  difficulty settings to a private copy; honor configured out marks.
- Recheck paid eligibility immediately before a paid fallback.
- Derive free test-edit permission from task text; record the actual final
  free fallback backend when delivery succeeds.

Regression checks use real temporary Git repositories and pytest suites with
scripted backends. They prove a broken baseline produces zero model calls,
remains queued, is checked only once per run, and works after main is repaired.
They also prove healthy baseline caching, worker tests, configuration forwarding
and a paid quota change preventing a model call.

Validation: full suite 1056 passed in 166.82s; smoke 36/36; focused 107
passed; after integrating planner PR44, Night/Job/CLI 63 passed; clean diff check.
Repair is merged and deployed through the installed main editable checkout.
Existing failed job branches and state are retained for review; no paid queue
restart or claim that a real free model has successfully coded a job.
