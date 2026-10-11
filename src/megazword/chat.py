"""Interactive, compact conversations over the normal one-shot router."""

from __future__ import annotations

import sys
from typing import Callable

from . import config
from .backends import Backend
from .memory import Memory, project_name
from .rater import Rating

HISTORY_TURNS = 3
HISTORY_CHARS = 4000
TURN_CHARS = 800


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit - 3].rstrip() + "..."


def _conversation(turns: list[tuple[str, str]]) -> str:
    recent = turns[-HISTORY_TURNS:]
    exchanges = [f"User: {_clip(user, TURN_CHARS)}\nAI: {_clip(answer, TURN_CHARS)}"
                 for user, answer in recent]
    while exchanges and len("[Conversation so far]\n" + "\n".join(exchanges)) > HISTORY_CHARS:
        exchanges.pop(0)
    return "[Conversation so far]\n" + "\n".join(exchanges)


def _read_message(read: Callable[[str], str]) -> str:
    parts = []
    while True:
        line = read("... " if parts else "mz> ")
        if line == "<<<" and not parts:
            while True:
                line = read("... ")
                if line == ">>>":
                    return "\n".join(parts).strip()
                parts.append(line)
        if line.endswith("\\"):
            parts.append(line[:-1])
            continue
        parts.append(line)
        return "\n".join(parts).strip()


def run(backends: dict[str, Backend], cfg: config.Config,
        rater: Callable[[str], Rating], statuses: Callable[[], dict] | None = None,
        read: Callable[[str], str] = input, write: Callable[[str], None] = print,
        project: str | None = None) -> int:
    """Run chat until /quit or terminal EOF/interrupt. Input and output are injectable."""
    from . import cli

    memory = Memory(config.HOME, project or project_name())
    turns: list[tuple[str, str]] = []
    pinned: str | None = None
    use_context = False
    write("Mega Zword chat. Type /help for commands.")
    while True:
        try:
            message = _read_message(read)
        except (EOFError, KeyboardInterrupt):
            write("")
            return 0
        if not message:
            continue
        if message.startswith("/"):
            command, _, arg = message.partition(" ")
            arg = arg.strip()
            if command == "/quit":
                return 0
            if command == "/help":
                write("/help /quit /retry /model <name> /auto /usage /note <text> "
                      "/decide <text> /history /context on|off /clear")
            elif command == "/model":
                if not arg:
                    write("Models: " + ", ".join(backends))
                elif arg not in backends:
                    write(f"Unknown AI '{arg}'. Choose from: {', '.join(backends)}")
                else:
                    pinned = arg
                    write(f"Pinned to {arg}.")
            elif command == "/auto":
                pinned = None
                write("Automatic model selection is on.")
            elif command == "/usage":
                cli.show_usage()
            elif command in ("/note", "/decide"):
                if not arg:
                    write(f"Usage: {command} <text>")
                else:
                    memory.add("decision" if command == "/decide" else "note", arg)
                    write(f"[megazword] saved to {memory.project} memory")
            elif command == "/history":
                entries = memory.recent(20)
                if not entries:
                    write("No project memory yet.")
                for entry in entries:
                    write(f"{entry.time[:16]}  {entry.by:8} {entry.kind:8} {entry.text}")
            elif command == "/context":
                if arg not in ("on", "off"):
                    write("Usage: /context on|off")
                else:
                    use_context = arg == "on"
                    write(f"Project memory context {arg}.")
            elif command == "/clear":
                turns.clear()
                write("Conversation cleared.")
            elif command == "/retry":
                class Args:
                    model = None
                answer: list[str] = []
                code = cli.retry_last(Args(), backends, cfg,
                                      on_answer=lambda text: (answer.append(text), write(text)))
                try:
                    import json
                    last = json.loads(cli.last_run_path().read_text(encoding="utf-8"))
                    if code == 0:
                        turns.append((last["prompt"], last["answer"]))
                except (OSError, ValueError, KeyError):
                    pass
            else:
                write(f"Unknown command '{command}'. Type /help for commands.")
            continue

        prompt = message
        sections = []
        if turns:
            sections.append(_conversation(turns))
        if use_context:
            block = memory.context_block()
            if block:
                sections.append(block)
        sections.extend(("[New message]", message))
        sent = "\n\n".join(sections)
        rating = None
        if pinned:
            chain = [backends[pinned]]
            write(f"[megazword] using {pinned} (pinned)")
        else:
            rating = rater(message)  # rate the new message, not the whole chat
            chain = cli.candidates(rating, cfg.route, backends,
                                   (statuses or cli.plan_statuses)(), cfg.out_now())
            if not chain:
                write(f"[megazword] no installed AI for a {rating.level} task")
                continue
            write(f"[megazword] rated {rating.level} ({rating.reason}) -> using {chain[0].name}")
        answer: list[str] = []
        code = cli.execute(sent, prompt, chain, cfg, memory, rating, forced=bool(pinned),
                           on_answer=lambda text: (answer.append(text), write(text)))
        if code == 0 and answer:
            turns.append((message, answer[0]))
            turns[:] = turns[-HISTORY_TURNS:]

