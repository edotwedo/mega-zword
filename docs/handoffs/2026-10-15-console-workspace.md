# Console workspace and project-context boundaries

Owner: Testlog-14 (Codex), 2026-10-15. Phil requested a simpler Matrix console
and asked that unrelated private history never appear in job responses.

The unrelated research excerpt Phil saw came from this Codex session's broad
memory lookup, not Mega Zword's backend output. No unrelated excerpt was sent
to a model by this update. Stop broad workspace-memory lookups for this job.

Home/Hive/chat now use green monospace on black, a transcript above the prompt,
and expandable options. Existing IDs, editing controls, Compare, pause, worker
inboxes, chat management and keyboard shortcuts remain available. Home output
is chronological; following output preserves a reader who has scrolled up.

Audit: normal CLI project memory is opt-in; tab history belongs to the tab and
opt-in memory belongs to its project. Mega Zword does not read Codex's general
memory registry. Two separate weaknesses were found and repaired: Home mixed
jobs from different projects, and dashboard Retry replayed a global last run.
Jobs now carry project metadata; displayed output and ongoing polling respect
the selected project. Per-project last-run files isolate Retry, including a
matching-project check before migrating legacy data. CLI retry -p selects the
same boundary; plain CLI retry intentionally remains global for compatibility.
One-shot instructions also tell models not to retrieve unrelated personal notes.

Regression tests send distinctive private markers through fake backends and
verify they never enter another project's Retry/output or another tab's prompt.
Opted-out project memory stays out; opted-in memory comes only from that project.
These checks do not prove that every provider will always stay on topic. Native
CLI startup rules and provider behavior still need review before public packaging;
no claim of perfect semantic output filtering is made.

Validation/deployment: see STATUS for final counts/build. No AI inference,
visible windows, desktop switches or focus moves. Headless Chrome/Edge returned
no DOM or screenshot; the browser connector lacks hidden-tab support, so physical
appearance is not claimed visually verified. Static/JS/accessibility tests cover
the layout and controls. Phil can visually check by closing/reopening the same
Mega Zword shortcut after installation. Preview helper was stopped. No reboot.
CODEX_JOB.md stays untracked. Preserve prior camera/terminal handoff limitations.

Delivery: source7c04108 installed in app venv and system Python311. All57 package/UI files match source in both, and all six Tencent identities remain. Desktop/Start Menu shortcuts label7c04108; backups retained. Full1283 passed (186.47s), final tabs/run-control28 passed (including the extra context test), layout/accessibility98 passed. Local Gitea main and codex/console-layout-2026-10-15 saved. No GitHub source mirror for this routine update. Claim released. Phil closes/reopens app and visually checks it.
