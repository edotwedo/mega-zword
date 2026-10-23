# Task file leases (M2)

`megazword task new --title "Fix a thing" --files src/megazword/example.py tests/test_example.py`
allocates a task ID, a `task/<id>` branch from HEAD, and file leases. It prints JSON;
it does not switch any checkout. Switch your own worktree to the printed branch
before committing the task's work. Keep `MEGAZWORD_SEAT` set to your designation.

`megazword task beat <id>` renews the owner's lease for 30 minutes and increments
its tick. `--files path/to/another.py` adds files if they are free. An expired or
released task cannot be revived: allocate a new task. No scheduler is installed;
the future supervisor can call this command for actual worker heartbeats.

`megazword task release <id>` relinquishes leases. It does not mark code reviewed,
merged or done. Only the owning seat can renew or release a task.

Worktrees in one Git repository share `.git/megazword-tasks.json` through Git's
common directory. Registry access is serialized and fails closed when busy or
invalid. File paths must remain inside the worktree. The approved hot files
(`src/megazword/cli.py`, `docs/STATUS.md`, `docs/HIVE-ROSTER.md`) never get leases.

The pre-push gate checks the commits being pushed against active leases both
before and after the suite. Another task's files block the push, including new
branches, deletions and renames. A task's own branch is allowed only for its owner.
Install the tracked hook with `megazword gate --install` in each participating repo.

This is cooperative local push enforcement, not an operating-system editor lock
or a remote server authorization boundary. An arbitrary editor can still change
a working file; stale/uninstalled hooks and Git's deliberate hook escapes are
not prevented by a client hook. Do not call those cases protected. The integrator
must arrange lease release after accepting the task and before its own push; the
serial merge queue and its review records remain separate M1/M3 work.
