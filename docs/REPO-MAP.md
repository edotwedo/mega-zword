# Repo map (design only)

Owner of this doc: Gauge-18. Owner of the code: Juniper-16
(`src/megazword/repo_map.py`, tests, and the later prompt hook).
Do not edit `agent.py` in this change. The hook lands after roadmap #1.

Source: `docs/INSPIRATION.md` item 17. Aider's idea: a ranked map of key
symbols, about 1–2k tokens, instead of dumping files into a prompt.

## What it is

A pure function from a repo root to a short text map.

- Input: repo root, a token budget (default 1500), an optional list of
  path prefixes to prefer (the files the job already named).
- Output: plain text, one symbol per line:
  `path:line  kind  name  [parent]`
  Kinds are function, class, and method. Nothing else.
- Rank: symbols in the preferred paths first, then the rest by how many
  other files reference the name. Ties break by path.
- Cut the list so the text stays under the budget. Never truncate a line.

Python only for the first version. Regex is enough (`def`, `class`,
`async def`). No tree-sitter and no network.

## What it is not

- Not a second copy of the file. The map names symbols. The model still
  opens a file when it needs the body.
- Not a search index and not a call graph drawn in full. A reference
  count is only a sort key.
- Not sent on every step. One map per job, cached on disk under the job
  directory, rebuilt when a preferred file's mtime changes.

## Done when

- `repo_map.py` returns a stable string under the budget for a fixture
  repo, with preferred paths ranked first.
- A test shows a name that appears in more files outranks a name that
  appears in one.
- The prompt hook is a separate, later edit. This doc does not add it.
