# Hive workers and recurring restore errors — Testlog-14

Phil asked for workers to appear in Hive, targeted messages/announcements, and
handoffs to an actual reachable session. A provider's one-shot room bot and an
old STATUS designation are not a worker connection.

## Implemented

- Hive lists native conversation IDs from held writer locks / verified PIDs,
  plus persistent MCP worker connections. Names come from session-linked reports;
  unidentified native sessions stay identified by client and exact session ID.
- Reused PIDs and saved reports do not count as live. Offline reports are grouped
  under a collapsed history section. Provider availability has a separate label.
- A recipient selector sends to an existing worker. Announce queues for all
  reachable workers, rather than starting fresh one-shot models. A disconnected
  recipient never silently becomes a room-bot recipient; drafts are retained.
- MCP workers register on hive_status/hive_say and receive addressed messages in
  hive_read/hive_wait/status responses. Repeated generic Codex labels get separate
  connection IDs. Workspace dependencies remain optional for basic CLI installs.
- Updated managed relays receive their own inbox only after the native client is
  idle, output is quiet and there is no draft/paste. Delivery is acknowledged after
  the input write; it does not mean the AI has replied or completed the request.
- Reports accept --session / the MCP session field; MEGAZWORD_SESSION and
  CODEX_THREAD_ID provide defaults. This links a designation to its real session.

## Popup containment applied without UI takeover

The observed Grok/Claude launches failed with Terminal 0x80070002 even though the
named interpreter and manifest exist. Exact cause is not yet proven. Launcher
commands now explicitly separate Terminal options from the child command with
`--`. A request is recorded as requested, never falsely counted as an opened tab.
Unconfirmed requests cannot automatically repeat; Restore Hive explicitly retries.

Stopped only owned pythonw boot helper20644 after validating its exact entry-point
arguments. Started replacement windowless watch helper24792. Fresh camera status
was verified after its start. Seeded retry guards for the two observed failed
sessions; automatic preview now requests ZERO new tabs. Existing terminal chats,
focus and desktops were not touched. Owner-return summaries continue separately
from suppressed launch retries. No model was called for these checks.

## Verification and next step

Source6608cae saved on local Gitea main/seat branch. Built wheel installed in both
dashboard venv and system Python311; all eight app/worker source/UI files in the
dashboard installation byte-match this checkout. Desktop and Start Menu shortcuts
show build6608cae, with previous shortcuts backed up. No app window was opened,
closed or restarted by this seat. Reopening the app is Phil's next step.

Full suite1267 passed (191.63s); final worker/UI checks19 passed after optional-
dependency and disconnected-recipient checks. Private real two-ConPTY tests cover
character Backspace and addressed-message delivery. Headless Chrome exercised the
actual authenticated UI POST with an isolated fake worker, verified no room bot
started, and checked recipient/draft preservation after disconnect. Screenshot:
build/workers-hive.png (fixture data). Diff check clean.

Live read-only inventory currently finds FOUR Codex sessions; this Testlog session
is linked by exact ID, other unreported names remain unknown. Their already-open
relays lack inbox support, so they MUST NOT be labelled reachable. Reopen the app
to load the installed UI. Keep terminal chats open until Phil is ready to test
one missing-tab restore; warn before any windows, desktop switches or focus moves.
Only then reload remaining managed tabs for inbox support. No Windows reboot is
required. Non-owner camera rejection and the exact Terminal launch fix still need
physical/user-driven confirmation. CODEX_JOB.md remains untracked.
