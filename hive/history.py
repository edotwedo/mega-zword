"""Chat history search (Phil, 2026-10-28): index Phil's exported AI conversations once,
then search them without reading them all again. Internal Hive tool: never shipped.

    python hive/history.py index <folder>        add or refresh every export under <folder>
    python hive/history.py search "words" [-n 10] [--source chatgpt]
    python hive/history.py show <conversation-id> [--find "words"]
    python hive/history.py stats

Reads ChatGPT and Claude `conversations.json` exports, and falls back to a generic
reader for other JSON (Grok, Gemini Takeout) and for .md/.txt/.html files. Unchanged
files are skipped on re-index. The index lives in ~/.megazword/history/index.sqlite and
never leaves the machine; the exports themselves are never copied or committed.
Plain words match all of them (W-2 works as typed); also "exact phrase", a OR b, tax*.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

TEXT_SUFFIXES = {".md", ".txt", ".html", ".htm"}
TEXT_KEYS = ("text", "content", "message", "prompt", "response", "query", "title", "parts")
SHOW_LIMIT = 200  # messages printed by `show`, so one huge chat cannot flood a bot


def db_path() -> Path:
    return Path.home() / ".megazword" / "history" / "index.sqlite"


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, stamp TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY, file TEXT NOT NULL, source TEXT NOT NULL, conv TEXT NOT NULL,
            title TEXT, time TEXT, role TEXT, seq INTEGER NOT NULL, text TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS messages_conv ON messages(conv, seq);
        CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(
            title, text, content='messages', content_rowid='id');
        CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
            INSERT INTO search(rowid, title, text) VALUES (new.id, new.title, new.text); END;
        CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
            INSERT INTO search(search, rowid, title, text) VALUES ('delete', old.id, old.title, old.text); END;
    """)
    return db


def when(value) -> str:
    """ISO date from an epoch number or an ISO string; '' when unknown."""
    if isinstance(value, (int, float)) and value > 0:
        return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    if isinstance(value, str) and value:
        return value[:16].replace("T", " ")
    return ""


def flatten(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(t for t in (flatten(v) for v in value) if t)
    if isinstance(value, dict):
        return "\n".join(t for t in (flatten(value[k]) for k in TEXT_KEYS if k in value) if t)
    return ""


def chatgpt(convs: list) -> list[dict]:
    out = []
    for c in convs:
        conv = c.get("id") or c.get("conversation_id") or ""
        nodes = [n.get("message") for n in (c.get("mapping") or {}).values() if n.get("message")]
        nodes.sort(key=lambda m: m.get("create_time") or 0)
        for m in nodes:
            text = flatten((m.get("content") or {}).get("parts") or (m.get("content") or {}).get("text") or "")
            if text.strip():
                out.append(dict(source="chatgpt", conv=f"chatgpt:{conv}", title=c.get("title") or "",
                                time=when(m.get("create_time") or c.get("create_time")),
                                role=(m.get("author") or {}).get("role", ""), text=text))
    return out


def claude(convs: list) -> list[dict]:
    out = []
    for c in convs:
        conv = c.get("uuid") or ""
        for m in c.get("chat_messages") or []:
            text = m.get("text") or flatten(m.get("content") or "")
            if text.strip():
                out.append(dict(source="claude", conv=f"claude:{conv}", title=c.get("name") or "",
                                time=when(m.get("created_at") or c.get("created_at")),
                                role=m.get("sender", ""), text=text))
    return out


def generic(data, source: str, conv: str) -> list[dict]:
    """Any other JSON: one message per dict that carries text, in document order."""
    out = []

    def walk(node, title=""):
        if isinstance(node, dict):
            title = node.get("title") if isinstance(node.get("title"), str) else title
            own = "\n".join(node[k] for k in TEXT_KEYS if isinstance(node.get(k), str) and k != "title")
            if own.strip():
                out.append(dict(source=source, conv=conv, title=title or "", role=str(node.get("role") or node.get("sender") or node.get("author") or "")[:40],
                                time=when(node.get("create_time") or node.get("created_at") or node.get("time") or node.get("timestamp")),
                                text=own))
            for v in node.values():
                if isinstance(v, (dict, list)):
                    walk(v, title)
        elif isinstance(node, list):
            for v in node:
                walk(v, title)

    walk(data)
    return out


def guess_source(path: Path) -> str:
    low = str(path).lower()
    for name in ("chatgpt", "openai", "claude", "anthropic", "grok", "gemini", "bard", "copilot", "perplexity"):
        if name in low:
            return {"openai": "chatgpt", "anthropic": "claude", "bard": "gemini"}.get(name, name)
    return path.parent.name.lower() or "other"


def read_file(path: Path) -> list[dict]:
    source = guess_source(path)
    conv = f"{source}:{hashlib.sha1(str(path).encode()).hexdigest()[:12]}"
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        if isinstance(data, list) and data and isinstance(data[0], dict):
            if "mapping" in data[0]:
                return chatgpt(data)
            if "chat_messages" in data[0]:
                return claude(data)
        return generic(data, source, conv)
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() in (".html", ".htm"):
        text = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", text)))
    chunks = [c.strip() for c in re.split(r"\n\s*\n", text) if c.strip()]
    return [dict(source=source, conv=conv, title=path.stem, time="", role="", text=c) for c in chunks]


def index(folder: Path, db: sqlite3.Connection, write=print) -> tuple[int, int]:
    added = skipped = 0
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        if path.suffix.lower() not in TEXT_SUFFIXES | {".json"}:
            continue
        stat = path.stat()
        stamp = f"{stat.st_size}:{int(stat.st_mtime)}"
        key = str(path.resolve())
        row = db.execute("SELECT stamp FROM files WHERE path=?", (key,)).fetchone()
        if row and row[0] == stamp:
            skipped += 1
            continue
        try:
            messages = read_file(path)
        except (ValueError, OSError) as exc:
            write(f"skip {path}: {type(exc).__name__}")
            continue
        db.execute("DELETE FROM messages WHERE file=?", (key,))
        seq = {}
        for m in messages:
            seq[m["conv"]] = seq.get(m["conv"], 0) + 1
            db.execute("INSERT INTO messages(file, source, conv, title, time, role, seq, text) "
                       "VALUES (?,?,?,?,?,?,?,?)",
                       (key, m["source"], m["conv"], m["title"], m["time"], m["role"], seq[m["conv"]], m["text"]))
        db.execute("INSERT OR REPLACE INTO files(path, stamp) VALUES (?,?)", (key, stamp))
        db.commit()
        added += 1
        write(f"indexed {path.name}: {len(messages)} messages")
    return added, skipped


def to_fts(query: str) -> str:
    """Plain words are quoted so 'W-2' or 'U.S.' just match; quotes, OR/AND/NOT or * keep FTS5 syntax."""
    if '"' in query or "*" in query or re.search(r"\b(OR|AND|NOT)\b", query):
        return query
    return " ".join('"' + word.replace('"', '') + '"' for word in query.split())


def search(db: sqlite3.Connection, query: str, limit: int = 10, source: str | None = None) -> list[tuple]:
    query = to_fts(query)
    sql = ("SELECT m.conv, m.source, m.title, m.time, m.role, "
           "snippet(search, 1, '[', ']', ' ... ', 24) FROM search JOIN messages m ON m.id = search.rowid "
           "WHERE search MATCH ?" + (" AND m.source = ?" if source else "") + " ORDER BY rank LIMIT ?")
    return db.execute(sql, (query, source, limit) if source else (query, limit)).fetchall()


def show(db: sqlite3.Connection, conv: str, find: str | None = None) -> list[tuple]:
    rows = db.execute("SELECT seq, time, role, text FROM messages WHERE conv=? ORDER BY seq", (conv,)).fetchall()
    if find:
        rows = [r for r in rows if find.lower() in r[3].lower()]
    return rows[:SHOW_LIMIT]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="history", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("index").add_argument("folder", type=Path)
    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("-n", type=int, default=10)
    s.add_argument("--source")
    sh = sub.add_parser("show")
    sh.add_argument("conv")
    sh.add_argument("--find")
    sub.add_parser("stats")
    args = parser.parse_args(argv)
    db = connect()
    if args.cmd == "index":
        if not args.folder.is_dir():
            print(f"not a folder: {args.folder}", file=sys.stderr)
            return 2
        added, skipped = index(args.folder, db)
        print(f"done: {added} files indexed, {skipped} unchanged")
    elif args.cmd == "search":
        try:
            rows = search(db, args.query, args.n, args.source)
        except sqlite3.OperationalError as exc:
            print(f"bad search: {exc} (quote phrases, e.g. '\"tax return\"')", file=sys.stderr)
            return 2
        for conv, source, title, time, role, snip in rows:
            print(f"{time or '?':16}  {source:8}  {title[:60]}\n    {role}: {snip}\n    id: {conv}")
        if not rows:
            print("no matches")
    elif args.cmd == "show":
        for seq, time, role, text in show(db, args.conv, args.find):
            print(f"--- #{seq} {role} {time}\n{text}")
    else:
        for source, convs, msgs in db.execute(
                "SELECT source, COUNT(DISTINCT conv), COUNT(*) FROM messages GROUP BY source ORDER BY 3 DESC"):
            print(f"{source:10} {convs:6} conversations  {msgs:8} messages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
