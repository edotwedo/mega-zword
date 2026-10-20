"""One-shot: tell every hive seat to pause and read Q or Hive.

Hive MCP `hive_wait` sessions see the post on the next wait. Native CLI
windows that are mid-turn are not injected — Phil still owns those.
No @mentions (that used to spawn one-shots / wake GitHub bots).
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import config
from .filelock import write_atomic
from .guard import scrub

_MENTION = re.compile(r"@[\w-]+")


def path(home: Path | None = None) -> Path:
    return (home or config.HOME) / "announce.json"


def clean(text: str) -> str:
    text = scrub((text or "").strip())
    text = _MENTION.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def banner(text: str) -> str:
    return f"ANNOUNCE: {text} Stop new work until you have read it."


def _toast(title: str, body: str) -> None:
    if sys.platform != "win32":
        return
    def q(s: str) -> str:
        return "'" + s.replace("'", "''")[:200] + "'"
    import subprocess
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
         "Add-Type -AssemblyName System.Windows.Forms; "
         "Add-Type -AssemblyName System.Drawing; "
         "$n = New-Object System.Windows.Forms.NotifyIcon; "
         "$n.Icon = [System.Drawing.SystemIcons]::Information; "
         "$n.Visible = $true; "
         f"$n.ShowBalloonTip(5000, {q(title)}, {q(body)}, "
         "[System.Windows.Forms.ToolTipIcon]::Info); "
         "Start-Sleep -Milliseconds 600; $n.Dispose()"],
        check=False, capture_output=True, timeout=12,
    )


def ping(body: str, cfg: config.Config | None = None) -> None:
    """Best-effort ntfy + Windows balloon. Never fail the announce."""
    try:
        topic = (cfg.ntfy_topic if cfg is not None else "") or ""
        if topic:
            from .sentinel import _ntfy
            _ntfy(topic, "Mega Zword", body)
    except (OSError, ValueError, TimeoutError):
        pass
    try:
        _toast("Mega Zword", body)
    except (OSError, ValueError, TimeoutError):
        pass
    # Wake every seat running `megazword room wait`: the Worker uses the same
    # "hive:<id>" signal on the PC topic, and any number wakes it.
    try:
        pc = os.environ.get("MEGAZWORD_NTFY_PC_TOPIC") or "megazword-hive-pc-pqymb6"
        req = urllib.request.Request(f"https://ntfy.sh/{pc}", data=b"hive:0", method="POST")
        urllib.request.urlopen(req, timeout=8).close()
    except (OSError, ValueError, TimeoutError):
        pass


def post(text: str, *, home: Path | None = None, room_name: str = "hive",
         cfg: config.Config | None = None,
         say: Callable | None = None,
         ping_fn: Callable[[str, config.Config | None], None] | None = None) -> str:
    from . import room
    cleaned = clean(text)
    if not cleaned:
        raise ValueError("need a message, e.g. megazword announce pause and read Q")
    body = banner(cleaned)
    (say or room.say)(room_name, body, author="floor", home=home, write=lambda _s: None)
    write_atomic(path(home), json.dumps({
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "text": cleaned,
        "body": body,
        "room": room_name,
    }) + "\n")
    (ping_fn or ping)(body, cfg)
    return body


def command(args, cfg: config.Config, write: Callable[[str], None] = print) -> int:
    raw = getattr(args, "text", None)
    if isinstance(raw, (list, tuple)):
        raw = " ".join(raw)
    raw = raw or getattr(args, "message", "") or ""
    room_name = getattr(args, "room", None) or "hive"
    try:
        body = post(str(raw), home=config.HOME, room_name=room_name, cfg=cfg)
    except ValueError as exc:
        write(f"announce: {exc}")
        return 2
    write(body)
    write("Posted to Hive. hive_wait seats see it now. Mid-turn CLIs still need a glance.")
    return 0


def add_parser(sub) -> None:
    p = sub.add_parser(
        "announce",
        help="one-shot: Hive + ping so seats pause and read Q/Hive",
    )
    p.add_argument("text", nargs="+", help="message, e.g. pause and read the Q update")
    p.add_argument("--room", default="hive", help="hive room name (default: hive)")
