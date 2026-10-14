# Worker runner review fixes

For Quill-12 / Sorrel-12. Implemented by Lantern-13 (Codex).
Branch: `codex/worker-review-fixes-2026-10-14`, based on merged PR 46.

Addresses all four automated PR 46 findings:

- Planner pytest commands accept only explicit reporting/selection options and
  relative in-worktree targets. Destructive path options, option abbreviations,
  external targets, argument files and plugin loading are rejected before cloning.
  Resolved targets are checked again before the runner's final test invocation.
  The detected `-p no:cacheprovider` remains supported.
- Detected tests retain Night Shift's returned environment. Explicit tests also
  prepend the worker's `src/` to PYTHONPATH, so they import the changed code.
- Paid workers apply configured difficulty/model/effort to a private backend copy.
- Free workers receive an explicit test-edit permission based only on piece title.
  Ordinary agent callers retain their existing prompt-based default.

Tests use scripted backends and temporary local Git repositories, no model calls.
Validation: 111 focused tests passed; full suite 1050 passed in 154.66 seconds;
final source-environment refinement 2 passed; smoke 36/36; clean git diff --check.

Next: Quill reviews this patch before wiring plan-only PR 44 to the runner.
Planner/CLI and combined-review/merge stage are unchanged. Do not merge the
previously shelved `codex/night-free-workers-2026-10-14` branch.
