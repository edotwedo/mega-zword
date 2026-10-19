"""Repo map: a ranked list of a project's key symbols, small enough to send to a model.

Models re-read whole files to find their way around (the 2026-10-17 trace: 61 of 62
calls were read_file). A map of class/function signatures, ranked by how often other
files use them, gives the same bearings in ~1-2k tokens. Regex only, no parser.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

DEFAULT_CHARS = 6000  # ~1.5k tokens
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
             ".expo", ".next", "coverage", ".mypy_cache", ".pytest_cache"}
MAX_FILE = 400_000
PY = re.compile(r"^( {0,4})(?:async\s+)?(class|def)\s+([A-Za-z]\w*)\s*(\([^)]*\)?)?")
JS = re.compile(r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?"
                r"(function\*?|class|interface|type|enum|const)\s+([A-Za-z]\w*)")
WORD = re.compile(r"[A-Za-z_]\w{3,}")
LANGS = {".py": "py", ".ts": "js", ".tsx": "js", ".js": "js", ".jsx": "js", ".mjs": "js"}


def _files(root: Path):
    for path in sorted(root.rglob("*")):
        if path.suffix not in LANGS or not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts[:-1]):
            continue
        try:
            if path.stat().st_size > MAX_FILE:
                continue
            yield rel.as_posix(), LANGS[path.suffix], path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue


def symbols(text: str, lang: str) -> list[tuple[int, str, str]]:
    """(line, name, short signature) for top-level defs and methods; private names skipped."""
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        if lang == "py":
            m = PY.match(line)
            if not m or m.group(3).startswith("_"):
                continue
            indent = "  " if m.group(1) else ""
            found.append((number, m.group(3), f"{indent}{m.group(2)} {m.group(3)}{m.group(4) or ''}"))
        else:
            m = JS.match(line)
            if not m or (m.group(1) == "const" and not line.startswith("export")):
                continue
            found.append((number, m.group(2), f"{m.group(1)} {m.group(2)}"))
    return [(n, name, sig[:100]) for n, name, sig in found]


def build(root, max_chars: int = DEFAULT_CHARS, focus=()) -> str:
    """Ranked map of root's source files, cut at max_chars. focus words boost matching files."""
    root = Path(root)
    files = [(rel, symbols(text, lang), Counter(WORD.findall(text))) for rel, lang, text in _files(root)]
    total = Counter()
    for _, _, words in files:
        total.update(words)
    focus = [f.lower() for f in focus if f]
    ranked = []
    for rel, syms, words in files:
        if not syms:
            continue
        # How often other files use this file's names: a cheap stand-in for importance.
        score = sum(total[name] - words[name] for _, name, _ in syms)
        hay = (rel + " " + " ".join(name for _, name, _ in syms)).lower()
        score += sum(1000 for f in focus if f in hay)
        ranked.append((-score, rel, syms))
    ranked.sort()
    out, size = [], 0
    for _, rel, syms in ranked:
        block = rel + ":\n" + "".join(f"  {n}: {sig}\n" for n, _, sig in syms)
        if size + len(block) > max_chars:
            if size == 0:  # first file alone is too big: keep what fits
                out.append(block[:max_chars].rsplit("\n", 1)[0] + "\n")
            break
        out.append(block)
        size += len(block)
    shown = len(out)
    if shown < len(ranked):
        out.append(f"[{len(ranked) - shown} more files not shown]\n")
    return "".join(out)


def add_parser(sub):
    p = sub.add_parser("map", help="ranked map of a repo's key symbols (small enough for a prompt)")
    p.add_argument("focus", nargs="*", help="words that move matching files to the top")
    p.add_argument("--root", default=".", help="project folder (default: here)")
    p.add_argument("--chars", type=int, default=DEFAULT_CHARS, help="size cap in characters")


def command(args) -> int:
    print(build(args.root, args.chars, args.focus), end="")
    return 0
