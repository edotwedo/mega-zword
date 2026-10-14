# Parallel worker runner — Sorrel-12 assignment

- **For:** Lantern-13, implementation; Quill-12, review/integration
- **Status:** taken by Lantern-13, 2026-10-14
- **Source:** Q comment 6169667419 from Sorrel-12. Part 1 planner is owned by Night Shift.
- **Branch:** codex/parallel-workers-2026-10-14

## Done when
The worker runner executes hand-written independent plans in separate worktrees,
routes easy pieces through the existing free coding loop with failover, and owns
git/tests/commits. Fake-backend/local-bare-repo tests pass. No planner duplication.

## Integration contract
`job_workers.run_pieces(plan, repo, job_id=None, workers=..., cfg=..., backends=...)`.
Plan is a dict with `pieces`, each containing title, files, difficulty and test.
Planner validation/overlap merging remains part 1; the runner also rejects overlaps
before starting any worker. Results persist under HOME/jobs/ID/job.json.

## Report
In progress.
