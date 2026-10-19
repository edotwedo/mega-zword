# Hive backup and recovery

Audit: 2026-10-18, recovery-audit subagent of Codex session 01a12d3d.
These are separate stores. A Git push or a terminal snapshot does not back up the room.

| Store | Recovery coverage | Limits |
| --- | --- | --- |
| Cloud Worker D1 `messages` table | Shared authenticated room history | Transcript API omits `request_id`, schema and infrastructure; a transcript export is not a restorable D1 database dump. |
| `~/.megazword/rooms/<room>.jsonl` | Local cached history | May be stale or contain local-only records; not authoritative for current cloud history. |
| `~/.megazword/rooms/<room>.<binding>.queue.json` | Pending text and idempotency IDs | Bound to origin and credential; preserve separately before rotation. |
| `~/.megazword/workspace/snapshot.json` | Saved native sessions, folders, models and tab configuration | References native client session data; does not contain full transcripts or credentials. |
| Local Gitea repositories and database | Committed source, issues and coordination metadata | Same-PC storage; repository copies alone omit database, attachments, configuration and secrets. |

## Manual room transcript export

Use the existing `HIVE_ROOM_URL` / `[room].url` configuration and Keymaster's
`HIVE_ROOM_TOKEN`. No token is accepted on the command line or copied into export
metadata. The script only makes authenticated GET requests; it never flushes
queues, posts messages, changes the cache, rotates credentials or schedules work.

From a checkout with Mega Zword available to Python:

```powershell
$env:PYTHONPATH = 'src'
python scripts/backup_hive_room.py 'C:\Users\mrmar\PrivateHiveBackups\room-2026-10-18'
```

Choose a **new private directory** for each export, outside Git repositories and
public/synced sharing folders. The example directory is not automatically provisioned
or access-controlled: use storage with appropriate local permissions. Message text
can itself contain private information. The script does not claim to scrub old
messages or encrypt the resulting files.

The script pages from ID zero, rejects invalid/non-increasing IDs, and writes
`messages.json` plus `SHA256SUMS`. It reads the files back and verifies exact JSON
content and SHA-256. Success prints only count, last ID and checksum. Existing
destinations are refused. A failure during writing may leave a partial new directory;
preserve it for inspection and use a fresh destination to retry. Collection is a
moving transcript view, not a transactional D1 snapshot; writes after the final page
require another export. Nothing in this process proves an off-device copy exists.

For recovery, first verify the checksum and inspect the transcript privately.
There is deliberately no automatic import: reposting history would change author
identity, timestamps and retry IDs. Full D1 restoration requires a separate verified
database export and an isolated restore rehearsal before touching production.

## Preserve pending delivery

Before credential rotation or moving machines, stop initiating new sends and wait
for in-flight room commands to finish. Privately copy the entire
`~/.megazword/rooms` directory, preserving filenames and queue IDs. Do not edit or
delete undrained queues. `room show` is not a read-only backup operation: it may
flush queued sends. Under the same origin and credential, the normal client retries
with existing idempotency IDs. With a new credential, have Phil review pending text
and explicitly resend under the new identity; never rename queue files to bypass
their binding. A safe full-machine backup also needs separately protected credential
recovery and native client data; this transcript tool does not export credentials.

## Verified local recovery state

On October 18 the `MegaZword-WorkspaceSnapshot` scheduled task was **Disabled**,
last successful run October 16 at 12:58:41 PM PT (result 0). The saved snapshot has
that timestamp. The Startup folder contained only Ollama; Hive startup was absent.
Do not re-enable tasks as part of a backup: prior shutdown was Phil's instruction.

Desktop **Restore Hive** still exists. Its implementation is
`src/megazword/workspace.py`, documented in
[the terminal workspace handoff](handoffs/2026-10-15-terminal-workspace.md).
Latest `restore-status.json` (October 16, 1:01:13 PM PT) showed one requested,
zero opened, five earlier launches unconfirmed and one already open. The older
boot record says six requested, which is not proof all six clients resumed.
Interactive restoration needs Phil's readiness; this audit did not launch windows.

Selective rollback files exist in
`~/.megazword/backups/installed-update-20261015-094402` and
`%LOCALAPPDATA%/Gitea/migration`, including prior Git configuration and a Workshop
untracked snapshot. These are not comprehensive disaster recovery.

No dedicated full Hive/Gitea backup job, off-device copy or successful full restore
rehearsal was found in the examined Gitea/Workshop/Mega Zword documentation, scripts,
installation folders or Windows task metadata. Windows AppList/CloudRestore tasks
named Backup do not establish Hive coverage. Remaining work: select private backup
storage, preserve all stores consistently, and rehearse recovery in isolation.
Do not stop Gitea or replace production data to test a backup.
