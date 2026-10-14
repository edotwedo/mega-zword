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

- [x] edotwedo/mega-zword | In docs/GUIDE.md, section "Night Shift", add one bullet saying `megazword night status` shows whether the STOP file is set, if a run is going, the last 10 jobs and where the last summary is | done when: the bullet is in the Night Shift section and nothing else changed <!-- done 2026-10-13: night/2026-10-13-1 (live test run by Forge-13) -->
- [x] edotwedo/workshop | Joke alarm J1: in joke-alarm/RESEARCH.md add a section "Open questions for a refresh (night 2026-10-14)" listing what in the file is older than 30 days or has no source, and what to re-check (existing joke alarm apps, what comedy apps pay comics, Tacoma/Seattle open mics). Docs only; don't invent facts or numbers | done when: the new section exists, lists concrete items with the line they refer to, and nothing else in the repo changed <!-- done 2026-10-14: night/2026-10-14-1 -->
- [x] edotwedo/workshop | Joke alarm J2: write joke-alarm/ANDROID-ALARM-CHECK.md, a short checklist for a reliable Android alarm that plays audio (Expo dev build plus a native alarm module, exact-alarm permission and Google Play's policy for alarm apps, Doze, lock screen, audio focus). Mark every claim "to verify" with the doc to check; docs only | done when: the file exists with a checklist and a "to verify" list, and nothing else changed <!-- done 2026-10-14: night/2026-10-14-2 -->
- [x] edotwedo/mega-zword | Add tests to tests/test_night.py for `megazword night status` (STOP file shown, lock shown, last jobs from state.json, last summary path) and for `night resume` when no STOP file exists. Tests only; don't change src/ | done when: the new tests pass with the full suite and src/ is unchanged <!-- done 2026-10-13: grok/night-status-guide-2026-10-13 (Quill-12; also restored the GUIDE status bullet onto the real Night Shift section; do not merge night/2026-10-13-1, it wiped the section) -->
