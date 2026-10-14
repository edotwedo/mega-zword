"""Local activity and cooperative intervention for dashboard coding jobs."""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .filelock import locked, write_atomic
from .guard import scrub

ENV = "MEGAZWORD_RUN_CONTROL"


def safe(value):
    text = str(value)
    for name, secret in os.environ.items():
        if secret and re.search(r"KEY|TOKEN|SECRET|PASSWORD|ACCOUNT_ID", name, re.I):
            text = text.replace(secret, "[REDACTED]")
    return scrub(text)[:240]


class Control:
    def __init__(self, folder: Path):
        self.folder = folder
        self.commands = folder / "commands.json"
        self.activity = folder / "activity.json"

    @classmethod
    def from_env(cls):
        value = os.environ.get(ENV)
        if not value:
            return None
        folder = Path(value).resolve()
        if not folder.is_relative_to((config.HOME / "run-controls").resolve()):
            raise ValueError("run control folder must be under Mega Zword home")
        return cls(folder)

    @staticmethod
    def read(path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}

    def request(self, action, text=""):
        if action not in ("pause", "resume", "stop", "instruct"):
            raise ValueError("unknown run action")
        if action == "instruct" and (not isinstance(text, str) or not text.strip() or len(text) > 4000):
            raise ValueError("instruction must be 1 to 4000 characters")
        with locked(self.commands) as held:
            if not held:
                raise ValueError("run controls busy; try again")
            data = self.read(self.commands)
            if action in ("pause", "resume"):
                data["paused"] = action == "pause"
            elif action == "stop":
                data["stop"] = True
            else:
                pending = data.setdefault("instructions", [])
                if len(pending) >= 20:
                    raise ValueError("too many pending instructions")
                pending.append(text.strip())
            write_atomic(self.commands, json.dumps(data))

    def publish(self, phase, **details):
        with locked(self.activity) as held:
            if not held:
                raise RuntimeError("run activity lock unavailable")
            data = self.read(self.activity)
            event = {"time": datetime.now(timezone.utc).isoformat(), "phase": phase,
                     **{key: safe(value) for key, value in details.items()}}
            data.update(event)
            data["events"] = [*data.get("events", []), event][-40:]
            write_atomic(self.activity, json.dumps(data))

    def view(self):
        data = self.read(self.activity)
        commands = self.read(self.commands)
        return {**data, "pause_requested": bool(commands.get("paused")),
                "pending_instructions": len(commands.get("instructions", []))}

    def checkpoint(self):
        """Wait at a safe boundary; return queued directions and paused duration."""
        started = time.monotonic()
        paused = False
        while True:
            with locked(self.commands) as held:
                if not held:
                    raise RuntimeError("run controls lock unavailable")
                data = self.read(self.commands)
                if data.get("stop"):
                    raise RuntimeError("run stopped by user")
                if not data.get("paused"):
                    instructions = data.pop("instructions", [])
                    write_atomic(self.commands, json.dumps(data))
                    break
            if not paused:
                self.publish("paused")
                paused = True
            time.sleep(0.1)
        if paused:
            self.publish("resumed")
        if instructions:
            self.publish("instruction received", count=len(instructions))
        return instructions, time.monotonic() - started if paused else 0
