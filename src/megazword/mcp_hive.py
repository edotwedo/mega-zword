"""Stdio MCP server for the hive room: hive_read, hive_say, hive_wait.

JSON-RPC 2.0 framed with Content-Length headers (newline-delimited JSON is also
accepted; replies use the framing the request came in). stdout carries JSON-RPC only;
anything else goes to stderr. Run with `python -m megazword.mcp_hive`.
"""
from __future__ import annotations

import json
import math
import os
import sys
from typing import Any, BinaryIO

from . import __version__, floor, room

PROTOCOL_VERSION = "2024-11-05"
SUPPORTED_PROTOCOL_VERSIONS = (PROTOCOL_VERSION,)
SERVER_INFO = {"name": "megazword-hive", "version": __version__}
MAX_WAIT_SECONDS = 300.0
MAX_BODY_BYTES = 1_000_000  # same limit as the dashboard

TOOLS = [
    {
        "name": "hive_read",
        "description": "Read the last n messages of a hive room as lines \"[author] text\", "
                       "then \"(after=N)\": pass N to hive_wait.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "room": {"type": "string", "default": "hive"},
                "n": {"type": "integer", "default": 10},
            },
        },
    },
    {
        "name": "hive_say",
        "description": "Post a message to a hive room. No @mentions required. "
                       "Phil's @name picks the next room-start one-shot; bot @names do not.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "room": {"type": "string", "default": "hive"},
                "author": {"type": "string",
                           "description": "Defaults to $MEGAZWORD_SEAT or \"bot\"."},
            },
            "required": ["text"],
        },
    },
    {
        "name": "hive_wait",
        "description": "Block until a new message lands in a hive room (or timeout seconds pass). "
                       "Pass `after` from the last hive_read/hive_wait so nothing posted in "
                       "between is missed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "room": {"type": "string", "default": "hive"},
                "timeout": {"type": "number", "default": 120, "maximum": 300,
                            "description": "Seconds, capped at 300."},
                "after": {"type": "integer",
                          "description": "Message count from the last \"(after=N)\" line. "
                                         "Omit to wait for messages newer than now."},
            },
        },
    },
]


def log(text: str) -> None:
    print(f"[mcp_hive] {text}", file=sys.stderr, flush=True)


def _lines(messages: list) -> str:
    return "\n".join(f"[{m.author}] {m.text}" for m in messages)


def hive_read(args: dict) -> str:
    room_name = args.get("room") or "hive"
    n = int(args.get("n", 10))
    msgs = room.read_messages(room_name)
    if n <= 0 and msgs:  # like `floor peek -n 0`: cursor only
        return f"(after={len(msgs)})"
    recent = msgs[-n:] if n > 0 else []
    return f"{_lines(recent) or '(no messages yet)'}\n(after={len(msgs)})"


def hive_say(args: dict) -> str:
    text = str(args.get("text") or "").strip()
    if not text:
        raise ValueError("text is required")
    room_name = args.get("room") or "hive"
    author = args.get("author") or os.environ.get("MEGAZWORD_SEAT") or "bot"
    out: list[str] = []
    room.say(room_name, text, author=author, write=out.append)
    floor.hear(author)
    return "\n".join(out) or "posted"


def hive_wait(args: dict) -> str:
    room_name = args.get("room") or "hive"
    timeout = float(args.get("timeout", 120))
    if math.isnan(timeout):
        raise ValueError("timeout must be a number")
    # serve() is single-threaded: a huge wait would leave every other request unanswered.
    timeout = min(max(0.0, timeout), MAX_WAIT_SECONDS)
    after = args.get("after")
    # Pin the baseline here so the reply can carry the next cursor.
    after = len(room.read_messages(room_name)) if after is None else max(0, int(after))
    msgs = floor.wait_for(room_name, after=after, timeout=timeout)
    return f"{_lines(msgs) or '(no new hive message)'}\n(after={after + len(msgs)})"


HANDLERS = {"hive_read": hive_read, "hive_say": hive_say, "hive_wait": hive_wait}


def handle(request: dict) -> dict | None:
    """Return a JSON-RPC response, or None for notifications."""
    method = request.get("method")
    req_id = request.get("id")
    if "id" not in request:
        return None
    params = request.get("params") or {}

    def ok(result: Any) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def err(code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    if not isinstance(params, dict):
        return err(-32602, "params must be an object")
    if method == "initialize":
        floor.hear(os.environ.get("MEGAZWORD_SEAT") or "")
        # Echo a version we speak; otherwise offer ours and let the client decide.
        asked = params.get("protocolVersion")
        return ok({
            "protocolVersion": asked if asked in SUPPORTED_PROTOCOL_VERSIONS else PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        handler = HANDLERS.get(name)
        if handler is None:
            return err(-32602, f"unknown tool: {name}")
        try:
            text = handler(params.get("arguments") or {})
            return ok({"content": [{"type": "text", "text": text}], "isError": False})
        except Exception as e:  # a tool failure is a result, not a protocol error
            log(f"{name} failed: {e!r}")
            return ok({"content": [{"type": "text", "text": f"error: {e}"}], "isError": True})
    return err(-32601, f"method not found: {method}")


def safe_handle(message: Any) -> dict | None:
    """handle() that never raises: a bad message gets an error reply, not a dead server."""
    if not isinstance(message, dict):
        return {"jsonrpc": "2.0", "id": None,
                "error": {"code": -32600, "message": "invalid request"}}
    try:
        return handle(message)
    except Exception as e:
        log(f"handler crashed: {e!r}")
        if "id" not in message:  # notifications never get a reply
            return None
        return {"jsonrpc": "2.0", "id": message.get("id"),
                "error": {"code": -32603, "message": str(e)}}


def read_message(stream: BinaryIO) -> tuple[dict | None, bool] | None:
    """Read one message. Returns (message, framed) or None at EOF.
    message is None when the body isn't valid JSON or Content-Length is bad
    (missing, negative, or over MAX_BODY_BYTES)."""
    while True:
        line = stream.readline()
        if not line:
            return None
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith((b"{", b"[")):
            try:
                return json.loads(stripped.decode("utf-8")), False
            except ValueError:
                return None, False
        break
    headers = {}
    while stripped:
        key, _, value = stripped.decode("ascii", "replace").partition(":")
        headers[key.strip().lower()] = value.strip()
        line = stream.readline()
        if not line:
            return None
        stripped = line.strip()
    try:
        length = int(headers.get("content-length", ""))
    except ValueError:
        log(f"bad headers: {headers}")
        return None, True
    if length < 0:  # stream.read(-n) would block until stdin closes
        log(f"negative Content-Length: {length}")
        return None, True
    if length > MAX_BODY_BYTES:
        log(f"Content-Length too large: {length}")
        while length > 0:  # skip the body so the next message still lines up
            chunk = stream.read(min(length, 65536))
            if not chunk:
                return None
            length -= len(chunk)
        return None, True
    body = stream.read(length)
    if len(body) < length:
        return None
    try:
        return json.loads(body.decode("utf-8")), True
    except ValueError:
        return None, True


def write_message(stream: BinaryIO, message: dict | list, framed: bool) -> None:
    body = json.dumps(message, ensure_ascii=False).encode("utf-8")
    if framed:
        stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
    else:
        stream.write(body + b"\n")
    stream.flush()


def serve(stdin: BinaryIO | None = None, stdout: BinaryIO | None = None) -> int:
    stdin = stdin or sys.stdin.buffer
    stdout = stdout or sys.stdout.buffer
    while True:
        got = read_message(stdin)
        if got is None:
            return 0
        message, framed = got
        if message is None:
            write_message(stdout, {"jsonrpc": "2.0", "id": None,
                                   "error": {"code": -32700, "message": "parse error"}}, framed)
            continue
        if isinstance(message, list):  # batch: each item stands alone
            if not message:
                write_message(stdout, safe_handle(None), framed)
                continue
            replies = [r for r in (safe_handle(m) for m in message) if r]
            if replies:
                write_message(stdout, replies, framed)
            continue
        reply = safe_handle(message)
        if reply is not None:
            write_message(stdout, reply, framed)


if __name__ == "__main__":
    # Anything that prints by accident must not corrupt the JSON-RPC stream.
    _out = sys.stdout.buffer
    sys.stdout = sys.stderr
    sys.exit(serve(sys.stdin.buffer, _out))
