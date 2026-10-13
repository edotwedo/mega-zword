# Night Shift queue

`megazword night run` (and the nightly task) works through the open lines below, top to bottom.
Each job runs on its own branch `night/<date>-<n>`, never main. A lead reviews and merges.

One job per line: `- [ ] repo | task | done when: ... | test: command (optional)`
- `repo` is `owner/name` on GitHub (for example `edotwedo/mega-zword`).
- `task` is what the AI should change. Keep it small: one night job, one focused change.
- `done when` is how a reviewer can tell it worked.
- `test:` is optional. Without it, a Python repo with `tests/` runs pytest; others run no tests.
- `[ ]` waiting, `[x]` done, `[!]` failed. Night Shift ticks the boxes on a separate `night/` branch
  so the marks can be merged too. A finished or failed line is never run twice.

Phil or any bot adds lines here (by PR or on main).

## Jobs

- [ ] edotwedo/mega-zword | In docs/GUIDE.md, section "Night Shift", add one bullet saying `megazword night status` shows whether the STOP file is set, if a run is going, the last 10 jobs and where the last summary is | done when: the bullet is in the Night Shift section and nothing else changed
