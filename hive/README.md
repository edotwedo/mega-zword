# hive/ - internal Hive tools

Everything in this folder is for Phil's Hive only. It is **never shipped**: the release package
is built from `src/` alone, and `tests/test_hive_boundary.py` fails if `src/` ever imports from
here or the package build starts including this folder.

| Tool | What it does |
|---|---|
| `length_watch.py` | Claude Code hook. Warns a bot as its conversation fills up, and nudges Phil when he gets chatty. |
| `SORTING.md` | Draft: which `src/megazword` modules ship, go to a Dev edition, or stay Hive-only. |
