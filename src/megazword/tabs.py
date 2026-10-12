"""Chat tabs: one pinned AI (or Auto) per tab, stored in ~/.megazword/tabs.json.

Home and Hive stay in the UI. These are the extra chat tabs. History lives on
the tab (last few turns, same clip as `megazword chat`) and is also written
to answers.jsonl so a restart still has it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import chat, config
from .backends import Backend, apply_levels, grok_label
from .filelock import locked, write_atomic
from .memory import Memory, check_project, project_name
from .rater import Rating

MAX_TABS = 40
TITLE_CHARS = 80
AUTO = "auto"


def path() -> Path:
    return config.HOME / "tabs.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_unlocked(p: Path) -> dict:
    if not p.exists():
        return {"tabs": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"tabs": []}
    if not isinstance(data, dict) or not isinstance(data.get("tabs"), list):
        return {"tabs": []}
    return data


def _load() -> dict:
    p = path()
    if not p.exists():
        return {"tabs": []}
    with locked(p):
        return _read_unlocked(p)


def _update(change: Callable[[list[dict]], list[dict]]) -> list[dict]:
    """Read, change and write tabs.json under one lock, so two tabs answering at once
    (the dashboard is threaded) can't overwrite each other's history."""
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with locked(p):
        tabs = [t for t in (_tab(raw) for raw in _read_unlocked(p)["tabs"]) if t]
        out = change(tabs)
        write_atomic(p, json.dumps({"tabs": out}, indent=2) + "\n")
    return out


def _tab(raw) -> dict | None:
    if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
        return None
    history = raw.get("history") if isinstance(raw.get("history"), list) else []
    clean = []
    for turn in history:
        if isinstance(turn, dict) and turn.get("user") and turn.get("answer"):
            clean.append({"user": str(turn["user"]), "answer": str(turn["answer"]),
                          "backend": str(turn.get("backend") or "")})
    return {
        "id": raw["id"],
        "title": str(raw.get("title") or "Chat")[:TITLE_CHARS],
        "ai": str(raw.get("ai") or AUTO),
        "project": str(raw.get("project") or "default"),
        "created": str(raw.get("created") or _now()),
        "history": clean[-chat.HISTORY_TURNS:],
    }


def list_tabs() -> list[dict]:
    return [t for t in (_tab(raw) for raw in _load()["tabs"]) if t]


def _find(tabs: list, tab_id: str) -> dict:
    for tab in tabs:
        if tab["id"] == tab_id:
            return tab
    raise ValueError(f"no tab {tab_id!r}")


def _known_ai(name: str, backends: dict[str, Backend]) -> str:
    key = (name or AUTO).strip().lower()
    if key in ("", AUTO):
        return AUTO
    if key not in backends:
        raise ValueError(f"unknown AI {name!r}")
    return key


def create(ai: str = AUTO, project: str | None = None, title: str | None = None,
           backends: dict[str, Backend] | None = None) -> dict:
    pin = _known_ai(ai, backends) if backends is not None else (
        (ai or AUTO).strip().lower() or AUTO)
    proj = project or project_name()
    check_project(config.HOME, proj, {proj})
    label = (title or ("Auto" if pin == AUTO else pin)).strip()[:TITLE_CHARS] or "Chat"
    made: list[dict] = []

    def add(tabs: list[dict]) -> list[dict]:
        if len(tabs) >= MAX_TABS:
            raise ValueError(f"at most {MAX_TABS} chat tabs")
        n = 1
        ids = {t["id"] for t in tabs}
        while f"t{n}" in ids:
            n += 1
        made.append({"id": f"t{n}", "title": label, "ai": pin, "project": proj,
                     "created": _now(), "history": []})
        return [*tabs, made[0]]

    _update(add)
    return made[0]


def rename(tab_id: str, title: str) -> dict:
    label = title.strip()[:TITLE_CHARS]
    if not label:
        raise ValueError("empty title")

    def change(tabs: list[dict]) -> list[dict]:
        _find(tabs, tab_id)
        return [{**t, "title": label} if t["id"] == tab_id else t for t in tabs]

    return _find(_update(change), tab_id)


def close(tab_id: str) -> dict:
    def drop(tabs: list[dict]) -> list[dict]:
        _find(tabs, tab_id)
        return [t for t in tabs if t["id"] != tab_id]

    _update(drop)
    return {"ok": True, "id": tab_id}


def _conversation_prompt(tab: dict, message: str, context_block: str) -> str:
    turns = [(t["user"], t["answer"]) for t in tab["history"]]
    sections = []
    if turns:
        sections.append(chat._conversation(turns))
    if context_block:
        sections.append(context_block)
    sections.extend(("[New message]", message))
    return "\n\n".join(sections)


def send(tab_id: str, prompt: str, backends: dict[str, Backend], cfg: config.Config,
         rater: Callable[[str], Rating],
         statuses: Callable[[], dict] | None = None, context: bool = False) -> dict:
    """One chat turn on a tab. Same lean flags, timeouts, out marks and
    failure text as `megazword chat` (via cli.execute)."""
    from . import cli

    message = prompt.strip()
    if not message:
        raise ValueError("empty prompt")
    # Our own copy: apply_levels swaps entries, and the dashboard shares one dict
    # between threads, so another tab's model/effort must not leak into this run.
    backends = dict(backends)
    tab = _find(list_tabs(), tab_id)
    memory = Memory(config.HOME, tab["project"], cfg.memory_lines)
    block = memory.context_block() if context else ""
    sent = _conversation_prompt(tab, message, block)
    pin = tab["ai"]
    rating: Rating | None = None
    if pin != AUTO:
        if pin not in backends:
            raise ValueError(f"unknown AI {pin!r}")
        apply_levels(backends, "medium", cfg.grok, cfg.levels)
        chain = [backends[pin]]
        using = grok_label(chain[0])
        forced = True
    else:
        rating = rater(message)
        apply_levels(backends, rating.level, cfg.grok, cfg.levels)
        chain = cli.candidates(rating, cfg.route, backends,
                               (statuses or cli.plan_statuses)(), cfg.out_now())
        if not chain:
            return {"ok": False, "id": tab_id, "error":
                    f"no installed AI for a {rating.level} task", "answer": "",
                    "backend": None, "tab": tab}
        using = grok_label(chain[0])
        forced = False
    captured: list[str] = []
    code = cli.execute(sent, message, chain, cfg, memory, rating, forced=forced,
                       on_answer=captured.append, tab_id=tab_id)
    if code != 0 or not captured:
        return {"ok": False, "id": tab_id, "error": "no AI gave a usable answer",
                "answer": "", "backend": None, "using": using, "tab": tab}
    answer = captured[0]
    backend = chain[0].name
    try:
        last = json.loads(cli.last_run_path().read_text(encoding="utf-8"))
        backend = str(last.get("backend") or backend)
    except (OSError, ValueError):
        pass
    turn = {"user": message, "answer": answer, "backend": backend}

    def append(tabs: list[dict]) -> list[dict]:
        # Re-read at save time: other tabs may have answered, been renamed or closed
        # during this (possibly minutes-long) call. A tab closed meanwhile stays closed.
        return [{**t, "history": [*t["history"], turn][-chat.HISTORY_TURNS:]}
                if t["id"] == tab_id else t for t in tabs]

    tab = next((t for t in _update(append) if t["id"] == tab_id),
               {**tab, "history": [*tab["history"], turn][-chat.HISTORY_TURNS:]})
    return {"ok": True, "id": tab_id, "answer": answer, "backend": backend,
            "using": using, "tab": tab, "error": None}
