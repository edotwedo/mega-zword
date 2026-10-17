"""Name a new Codex conversation before opening its TUI; no model call needed."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime
import json
import os
from pathlib import Path
import queue
import re
import sqlite3
import subprocess
import sys
import threading
import time

HOME = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "MegaZword/CodexNames"
DATABASE = HOME / "designations.sqlite"
WORDS = ("Briar", "Clover", "Ember", "Linden", "Moss", "Nettle", "Rowan", "Sage",
         "Thistle", "Willow", "Aspen", "Fern", "Hazel", "Laurel", "Maple", "Sorrel")
SUBCOMMANDS = set("agents exec review login logout mcp plugin app-server remote-control app completion update doctor sandbox debug apply resume queue archive delete migrate-rollouts unarchive fork cloud exec-server features help".split())
VALUE_FLAGS = {"-c", "--config", "-m", "--model", "-p", "--profile", "-C", "--cd", "-s", "--sandbox", "-a", "--ask-for-approval", "--add-dir", "--remote", "--remote-auth-token-env", "--local-provider", "--enable", "--disable", "-i", "--image"}


def native_binary():
    root = Path(os.environ["APPDATA"]) / "npm/node_modules/@openai/codex"
    candidates = list(root.glob("node_modules/@openai/codex-win32-x64/vendor/*/bin/codex.exe"))
    candidates += list(root.glob("vendor/*/codex/codex.exe"))
    candidates = list(dict.fromkeys(p.resolve() for p in candidates if p.is_file()))
    if len(candidates) != 1:
        raise RuntimeError("Cannot identify one installed native Codex executable")
    return str(candidates[0])


def invocation(args):
    """Return new/resume/pass and target cwd without interpreting prompt text."""
    if any(a in ("-h", "--help", "-V", "--version") for a in args):
        return "pass", Path.cwd()
    cwd, i = Path.cwd(), 0
    while i < len(args):
        arg = args[i]
        if arg in VALUE_FLAGS:
            if i + 1 >= len(args):
                return "pass", cwd  # Native CLI reports the invalid option.
            if arg in ("-C", "--cd"):
                cwd = Path(args[i + 1]).expanduser().resolve()
            i += 2
            continue
        if arg.startswith("--cd="):
            cwd = Path(arg.partition("=")[2]).expanduser().resolve()
        elif arg in SUBCOMMANDS:
            return ("resume" if arg == "resume" else "pass"), cwd
        elif not arg.startswith("-") or arg == "--":
            return "new", cwd
        i += 1
    return "new", cwd


def designation(thread_id, existing=None, database=DATABASE):
    with closing(sqlite3.connect(database, timeout=10)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS names(thread_id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL)")
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT name FROM names WHERE thread_id=?", (thread_id,)).fetchone()
        if row:
            return row[0]
        # Preserve an established designation on resume. Ordinary auto-generated
        # topic titles are left untouched by the resume pass-through below.
        if existing:
            name = existing
        else:
            day = datetime.now().strftime("%d")
            for number in range(1, 100000):
                word = WORDS[(number - 1) % len(WORDS)]
                suffix = "" if number <= len(WORDS) else f"-{(number-1)//len(WORDS)+1:02d}"
                name = f"{word}-{day}{suffix}"
                if not db.execute("SELECT 1 FROM names WHERE name=?", (name,)).fetchone():
                    break
            else:
                raise RuntimeError("No unique designation available")
        db.execute("INSERT INTO names VALUES (?,?)", (thread_id, name))
        return name


class RPC:
    def __init__(self, binary):
        env = dict(os.environ)
        env.pop("MEGAZWORD_SESSION", None)
        env.pop("CODEX_THREAD_ID", None)
        self.process = subprocess.Popen([binary, "app-server", "--stdio"], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        text=True, encoding="utf-8", env=env,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.messages = queue.Queue()
        self.next_id = 0
        threading.Thread(target=self._read, daemon=True).start()
        self.call("initialize", {"clientInfo": {"name": "hive-session-namer", "title": "Hive named Codex launcher", "version": "1.0"}})
        self.send({"method": "initialized", "params": {}})

    def _read(self):
        for line in self.process.stdout:
            try:
                self.messages.put(json.loads(line))
            except ValueError:
                pass

    def send(self, value):
        self.process.stdin.write(json.dumps(value) + "\n")
        self.process.stdin.flush()

    def call(self, method, params):
        self.next_id += 1
        request_id = self.next_id
        self.send({"id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            try:
                message = self.messages.get(timeout=max(.1, deadline - time.monotonic()))
            except queue.Empty:
                break
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError("Codex metadata operation failed: " + method)
                return message.get("result", {})
        raise RuntimeError("Codex metadata operation timed out: " + method)

    def close(self):
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)


def prepare(binary, cwd, database=DATABASE):
    rpc = RPC(binary)
    try:
        result = rpc.call("thread/start", {"cwd": str(cwd)})
        sid = result["thread"]["id"]
        name = designation(sid, database=database)
        rpc.call("thread/name/set", {"threadId": sid, "name": name})
        saved = rpc.call("thread/read", {"threadId": sid, "includeTurns": False})["thread"]
        if saved.get("name") != name:
            raise RuntimeError("Saved designation did not verify")
        return sid, name
    finally:
        rpc.close()


def resume_environment(args, database=DATABASE):
    env = dict(os.environ)
    # Do not pass another live chat's identity into a resumed conversation.
    env.pop("MEGAZWORD_SEAT", None)
    env.pop("MEGAZWORD_SESSION", None)
    env.pop("CODEX_THREAD_ID", None)
    index = args.index("resume") + 1
    if index < len(args) and not args[index].startswith("-") and database.exists():
        with closing(sqlite3.connect(database, timeout=10)) as db:
            row = db.execute("SELECT thread_id,name FROM names WHERE thread_id=? OR name=?",
                             (args[index], args[index])).fetchone()
        if row:
            env.update(MEGAZWORD_SESSION=row[0], MEGAZWORD_SEAT=row[1])
    return env


def main(args):
    binary = native_binary()
    mode, cwd = invocation(args)
    if mode == "resume":
        return subprocess.call([binary, *args], env=resume_environment(args))
    if mode != "new":
        return subprocess.call([binary, *args])
    sid, name = prepare(binary, cwd)
    env = dict(os.environ, MEGAZWORD_SEAT=name, MEGAZWORD_SESSION=sid)
    env.pop("CODEX_THREAD_ID", None)
    print(f"Hive session: {name}", flush=True)
    # --cd remains honored and other interactive flags are passed through.
    # Configuration and permission choices are not replaced by the launcher.
    return subprocess.call([binary, "resume", sid, *args], env=env)


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        print(f"Hive naming could not start Codex: {exc}", file=sys.stderr)
        raise SystemExit(1)
