# How work lands (main only)

**One branch: `main`.** The newest commit on `main` is the current truth. There is no develop,
no release branch, no per-task branch, and nothing to merge.

Phil, 2026-10-27: *"why isn't there just a way to be like, 'fixed it, now the fixed one is 1a
and the shit one is called deaddonttouch'."* That is this document. Everything else was
ceremony that produced bugs of its own: commits landing on the wrong branch, orphaned commits
after a `checkout -B`, merge conflicts in generated docs, leases expiring under idle seats.

## The loop

1. A worker edits in its own **worktree** (isolation is a filesystem property, not a branch).
2. It commits **on main** and pushes.
3. The **pre-push gate** runs the suite. Red = the push is refused. That is the only gate.
   For RobinTHood the gate is `npx --no-install tsc --noEmit` instead.
4. A **free-model review** runs on the diff and is recorded in the log. It is evidence, not a
   veto: model prose cannot decide a merge, the suite can.

## Tags instead of branches

Want to keep an old state or park something broken?

```sh
git tag dead-dont-touch-<what>          # name the thing you are done with
git tag good-<date>                     # mark a known-good point
git push github --tags
```

The tag is the "deaddonttouch". Nothing else is needed.

## What was deleted, and why

| Removed | Reason |
|---|---|
| per-job task branches | wrong-branch commits, orphaned commits, endless merge queue |
| `scripts/merge_queue.py` | with one branch there is nothing to merge |
| 30-minute file leases | "who has this file" is a line in a file, not a lock with an expiry |
| `scripts/hive_poke.sh` | workers pull from a queue; nobody types into a chatbot to make it work |

## What stays

- The suite (the gate) and the RobinTHood typecheck.
- The free-model review, recorded per change.
- The work queue: `~/.megazword/night/local-jobs.json` + `scripts/night_local.py`.
- The Hive room, the meters and the guard.

Nothing here requires Phil to merge, review, resolve a conflict, or type a command.
