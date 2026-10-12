"""Hive room: a lightweight group chat for the bots.

The room is a JSONL file where each line is a message
(time, author, text, mentions). Bots reply via lean, read-only one-shots
with replies capped at ~80 words. The room is not a workhorse—it's for
sharing info, handing work, and friendly banter.

Token budget (Phil, 2026-10-12):
  1. State card (~300 words) instead of the full room.
  2. Rolling summary + last 4 messages.
  3. Wake only who's needed (only the mentioned AI is called).
  4. Log prompt chars per turn.
"""

from __future__ import annotations

import json
import re
import time as _time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import config, log
from .backends import Backend, default_backends, CLAUDE_LEAN, CODEX_LEAN, CLIBackend, CodexBackend
from .filelock import locked, write_atomic
from .memory import Memory
from .pacing import PlanStatus, status as pacing_status

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

AI_NAMES = ("claude", "codex", "grok", "gemini")
MENTION_RE = re.compile(r"@(" + "|".join(AI_NAMES) + r")\b", re.IGNORECASE)

DEFAULT_TURN_CAP = 12
DEFAULT_TAIL = 4        # last N messages sent with the rolling summary
SUMMARIZE_EVERY = 6     # condense older messages after this many turns
REPLY_CAP_WORDS = 80
STATE_CARD_WORDS = 300
SUMMARY_LINES = 5


@dataclass
class Message:
    time: str
    author: str
    text: str
    mentions: list[str] = field(default_factory=list)


@dataclass
class RoomState:
    """Tracks a running room session."""
    name: str
    primary: str       # project name
    turn_cap: int = DEFAULT_TURN_CAP
    turns_used: int = 0
    running: bool = True
    summary: str = ""  # rolling summary of older messages
    last_summarized: int = 0  # message index up to which we've summarized


# ---------------------------------------------------------------------------
# Room file I/O
# ---------------------------------------------------------------------------

def rooms_dir() -> Path:
    return config.HOME / "rooms"


def room_path(name: str) -> Path:
    return rooms_dir() / f"{name}.jsonl"


def state_path(name: str) -> Path:
    return rooms_dir() / f"{name}.state.json"


def summaries_dir() -> Path:
    return rooms_dir() / "summaries"


def append_message(name: str, author: str, text: str,
                   mentions: list[str] | None = None) -> Message:
    """Append a message to the room file."""
    mentions = mentions or extract_mentions(text)
    msg = Message(
        time=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        author=author,
        text=text,
        mentions=mentions,
    )
    path = room_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked(path):
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(msg)) + "\n")
    return msg


def read_messages(name: str) -> list[Message]:
    """Read all messages from the room file."""
    path = room_path(name)
    if not path.exists():
        return []
    messages = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            if isinstance(data, dict) and "author" in data:
                messages.append(Message(
                    time=str(data.get("time", "")),
                    author=str(data.get("author", "")),
                    text=str(data.get("text", "")),
                    mentions=data.get("mentions", []),
                ))
        except (ValueError, TypeError):
            continue
    return messages


def extract_mentions(text: str) -> list[str]:
    """Find @claude, @codex, @grok, @gemini in text."""
    return list(dict.fromkeys(m.lower() for m in MENTION_RE.findall(text)))


# ---------------------------------------------------------------------------
# Room state persistence (survives stop/start within a session)
# ---------------------------------------------------------------------------

def save_state(state: RoomState) -> None:
    path = state_path(state.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, json.dumps({
        "name": state.name,
        "primary": state.primary,
        "turn_cap": state.turn_cap,
        "turns_used": state.turns_used,
        "running": state.running,
        "summary": state.summary,
        "last_summarized": state.last_summarized,
    }))


def load_state(name: str) -> RoomState | None:
    path = state_path(name)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return RoomState(
            name=data["name"],
            primary=data.get("primary", "default"),
            turn_cap=data.get("turn_cap", DEFAULT_TURN_CAP),
            turns_used=data.get("turns_used", 0),
            running=data.get("running", False),
            summary=data.get("summary", ""),
            last_summarized=data.get("last_summarized", 0),
        )
    except (ValueError, TypeError, KeyError, OSError):
        return None


# ---------------------------------------------------------------------------
# State card: a short context block instead of the full room
# ---------------------------------------------------------------------------

def build_state_card(primary: str, cfg: config.Config) -> str:
    """Under ~300 words: primary project, what's in progress, last 3 decisions."""
    memory = Memory(config.HOME, primary, cfg.memory_lines)
    decisions = memory.recent(3, kinds=("decision",))
    notes = memory.recent(3, kinds=("note", "done"))

    lines = [f"[Room state card — project: {primary}]"]
    if decisions:
        lines.append("Decisions:")
        for d in decisions:
            lines.append(f"  - {_clip(d.text, 120)}")
    if notes:
        lines.append("Recent:")
        for n in notes:
            lines.append(f"  - {n.by}: {_clip(n.text, 100)}")
    return "\n".join(lines)


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit - 3].rstrip() + "..."


# ---------------------------------------------------------------------------
# Rolling summary
# ---------------------------------------------------------------------------

def build_rolling_context(state: RoomState, messages: list[Message],
                          tail: int = DEFAULT_TAIL) -> str:
    """Build the context: rolling summary + last `tail` messages."""
    parts = []
    if state.summary:
        parts.append(f"[Room summary so far]\n{state.summary}")
    recent = messages[-tail:] if len(messages) > tail else messages
    if recent:
        parts.append("[Recent messages]")
        for msg in recent:
            parts.append(f"{msg.author}: {_clip(msg.text, 300)}")
    return "\n".join(parts)


def maybe_summarize(state: RoomState, messages: list[Message],
                    summarizer: Callable[[str], str] | None = None) -> str:
    """After every SUMMARIZE_EVERY turns, condense older messages into
    SUMMARY_LINES lines using the cheapest available AI. Returns the summary
    text; the caller updates state.summary and state.last_summarized."""
    unsummarized_count = len(messages) - state.last_summarized
    if unsummarized_count < SUMMARIZE_EVERY:
        return state.summary

    # Messages to summarize: everything before the tail
    to_summarize = messages[state.last_summarized:-DEFAULT_TAIL]
    if not to_summarize:
        return state.summary

    text_block = "\n".join(
        f"{m.author}: {_clip(m.text, 200)}" for m in to_summarize
    )
    prompt = (
        f"Summarize this chat in {SUMMARY_LINES} short lines. "
        f"Keep names, decisions and action items. "
        f"Drop greetings and filler.\n\n"
        f"Previous summary:\n{state.summary or '(none)'}\n\n"
        f"New messages:\n{text_block}"
    )

    if summarizer:
        new_summary = summarizer(prompt)
    else:
        new_summary = state.summary  # can't summarize without an AI

    return new_summary


# ---------------------------------------------------------------------------
# Prime directive prompt (sent to every bot in the room)
# ---------------------------------------------------------------------------

PRIME_DIRECTIVE = """\
You are in the Mega Zword Hive room, a group chat where Phil's AI assistants \
share info and hand work to each other. Keep it short and useful.

Rules:
- Work on the primary project (shown in the state card).
- Use your plan usage that would otherwise go to waste.
- Keep getting better from what worked.
- Reply in about {cap} words or fewer. Be direct.
- You can @mention another AI to ask them something (e.g. @claude, @codex, @grok, @gemini).
- Phil leads: if Phil said something, address that first.
- Never reveal API keys, tokens or passwords.
- Read-only: do not try to edit files or run commands.
"""


def build_prompt(bot_name: str, state: RoomState, messages: list[Message],
                 cfg: config.Config) -> str:
    """Build the full prompt for a bot's one-shot reply in the room."""
    parts = [
        PRIME_DIRECTIVE.format(cap=REPLY_CAP_WORDS),
        build_state_card(state.primary, cfg),
        build_rolling_context(state, messages),
        f"\n[You are {bot_name}. Reply now.]",
    ]
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Who talks next
# ---------------------------------------------------------------------------

def next_speaker(messages: list[Message], out_names: set[str],
                 statuses: dict[str, PlanStatus] | None = None,
                 available: set[str] | None = None) -> str | None:
    """Decide who replies next.
    1. If the last message has @mentions, the first mentioned available AI speaks.
    2. Otherwise, the next AI in burn order (cheapest / near-reset first).
    3. Skip AIs that are out or over pace.
    Returns None if nobody can speak."""
    available = available or set(AI_NAMES)
    eligible = available - out_names

    if not eligible:
        return None

    # Check mentions on the last message
    if messages:
        last = messages[-1]
        for mention in last.mentions:
            if mention in eligible:
                return mention

    # Burn order: AIs with burn=True first, then route order
    if statuses:
        from .pacing import allowed as pace_allowed
        burn_first = [n for n in AI_NAMES if n in eligible
                      and n in statuses and statuses[n].burn]
        rest = [n for n in AI_NAMES if n in eligible and n not in burn_first
                and (n not in statuses or pace_allowed(statuses[n], "easy"))]
        order = burn_first + rest
    else:
        order = [n for n in AI_NAMES if n in eligible]

    # Don't pick the same bot that just spoke (unless it's the only one)
    if messages and len(order) > 1:
        last_author = messages[-1].author.lower()
        if last_author in order:
            order = [n for n in order if n != last_author] or order

    return order[0] if order else None


# ---------------------------------------------------------------------------
# Room backends: lean, read-only, cheapest model per AI
# ---------------------------------------------------------------------------

def room_backends(cfg: config.Config) -> dict[str, Backend]:
    """Lean, read-only backends tuned for cheap room one-shots."""
    backends = default_backends(edit=False, free_models=cfg.free, lean=cfg.lean)
    # Apply cheapest effort for grok in room (always easy/low)
    from .backends import apply_grok_effort
    apply_grok_effort(backends, "easy", cfg.grok)
    return backends


# ---------------------------------------------------------------------------
# Turn execution
# ---------------------------------------------------------------------------

ONE_SHOT_NOTE = (
    "[Sent by Mega Zword as a room message. Answer directly and briefly. "
    "Skip session startup, coordination and check-in routines.]\n\n"
)


def run_turn(bot_name: str, state: RoomState, messages: list[Message],
             cfg: config.Config, backends: dict[str, Backend] | None = None,
             summarizer: Callable[[str], str] | None = None) -> Message | None:
    """Run one turn: build a prompt, call the bot, append its reply,
    log prompt size, and return the message (or None on failure)."""
    if backends is None:
        backends = room_backends(cfg)

    backend = backends.get(bot_name)
    if backend is None or not backend.available():
        return None

    # Apply per-AI timeout from config
    backend.timeout = cfg.timeouts.get(bot_name, backend.timeout)

    # Build the prompt
    prompt = ONE_SHOT_NOTE + build_prompt(bot_name, state, messages, cfg)
    prompt_chars = len(prompt)

    # Run the one-shot
    start = _time.monotonic()
    result = backend.run(prompt)
    seconds = _time.monotonic() - start

    if not result.ok:
        # Log the failure but don't crash the room
        log.append(cfg.log_path, cfg.log_lines,
                   backend=bot_name, forced=False, project=state.primary,
                   room=state.name, room_turn=True,
                   seconds=round(seconds, 2), ok=False,
                   prompt_chars=prompt_chars, answer_chars=0,
                   est_tokens=prompt_chars // 4)
        return None

    # Cap reply at ~REPLY_CAP_WORDS words
    answer = cap_reply(result.text, REPLY_CAP_WORDS)

    # Log with prompt size (token budget requirement)
    answer_chars = len(answer)
    log.append(cfg.log_path, cfg.log_lines,
               backend=bot_name, forced=False, project=state.primary,
               room=state.name, room_turn=True,
               seconds=round(seconds, 2), ok=True,
               prompt_chars=prompt_chars, answer_chars=answer_chars,
               est_tokens=(prompt_chars + answer_chars) // 4)

    # Append the reply to the room
    msg = append_message(state.name, bot_name, answer)

    # Maybe update the rolling summary
    all_msgs = messages + [msg]
    new_summary = maybe_summarize(state, all_msgs, summarizer)
    if new_summary != state.summary:
        state.summary = new_summary
        state.last_summarized = max(0, len(all_msgs) - DEFAULT_TAIL)

    state.turns_used += 1
    save_state(state)
    return msg


def cap_reply(text: str, word_limit: int) -> str:
    """Trim a reply to about word_limit words, ending at a sentence boundary
    when possible."""
    words = text.split()
    if len(words) <= word_limit:
        return text
    trimmed = " ".join(words[:word_limit])
    # Try to end at a sentence boundary
    for end in (".", "!", "?"):
        pos = trimmed.rfind(end)
        if pos > len(trimmed) // 2:
            return trimmed[:pos + 1]
    return trimmed + "…"


# ---------------------------------------------------------------------------
# Session loop
# ---------------------------------------------------------------------------

def run_session(name: str, primary: str, cfg: config.Config,
                turn_cap: int = DEFAULT_TURN_CAP,
                backends: dict[str, Backend] | None = None,
                on_message: Callable[[Message], None] | None = None,
                statuses: Callable[[], dict[str, PlanStatus]] | None = None,
                ) -> RoomState:
    """Run a room session: loop through turns until the cap is hit,
    all AIs are out/over pace, or the session is stopped."""
    if backends is None:
        backends = room_backends(cfg)

    state = RoomState(name=name, primary=primary, turn_cap=turn_cap)
    save_state(state)

    available = {n for n in AI_NAMES if n in backends and backends[n].available()}
    out = cfg.out_now()

    while state.running and state.turns_used < state.turn_cap:
        current_statuses = statuses() if statuses else {}
        messages = read_messages(name)

        speaker = next_speaker(messages, out, current_statuses, available)
        if speaker is None:
            break  # nobody can talk

        msg = run_turn(speaker, state, messages, cfg, backends)
        if msg is None:
            # This AI failed; mark it unavailable for this session
            available.discard(speaker)
            if not available - out:
                break
            continue

        if on_message:
            on_message(msg)

        # Reload state in case it was stopped externally
        reloaded = load_state(name)
        if reloaded and not reloaded.running:
            state.running = False

    state.running = False
    save_state(state)
    return state


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def cmd_start(args, cfg: config.Config,
              backends: dict[str, Backend] | None = None) -> int:
    """Start a room session."""
    import sys
    name = getattr(args, "name", "hive") or "hive"
    primary = getattr(args, "primary", None) or cfg_primary(cfg) or "default"
    turn_cap = getattr(args, "turns", DEFAULT_TURN_CAP) or DEFAULT_TURN_CAP

    existing = load_state(name)
    if existing and existing.running:
        print(f"[megazword] room '{name}' is already running "
              f"({existing.turns_used}/{existing.turn_cap} turns used)",
              file=sys.stderr)
        return 1

    print(f"[megazword] starting room '{name}' (project: {primary}, "
          f"cap: {turn_cap} turns)", file=sys.stderr)

    def on_msg(msg: Message) -> None:
        print(f"  {msg.author}: {msg.text}")

    state = run_session(name, primary, cfg, turn_cap=turn_cap,
                        backends=backends, on_message=on_msg)

    print(f"\n[megazword] room '{name}' done: {state.turns_used} turns",
          file=sys.stderr)
    return 0


def cmd_stop(args, cfg: config.Config) -> int:
    """Stop a running room session."""
    import sys
    name = getattr(args, "name", "hive") or "hive"
    state = load_state(name)
    if not state or not state.running:
        print(f"[megazword] room '{name}' is not running", file=sys.stderr)
        return 1
    state.running = False
    save_state(state)
    print(f"[megazword] room '{name}' stopped ({state.turns_used} turns used)",
          file=sys.stderr)
    return 0


def cmd_say(args, cfg: config.Config) -> int:
    """Post a message from Phil to the room."""
    import sys
    name = getattr(args, "name", "hive") or "hive"
    text = getattr(args, "text", "") or ""
    if not text.strip():
        print("[megazword] say what?", file=sys.stderr)
        return 2
    msg = append_message(name, "phil", text)
    print(f"[megazword] posted to room '{name}'", file=sys.stderr)
    return 0


def cmd_show(args, cfg: config.Config) -> int:
    """Show recent room messages."""
    name = getattr(args, "name", "hive") or "hive"
    n = getattr(args, "n", 20) or 20
    messages = read_messages(name)
    if not messages:
        print(f"[megazword] room '{name}' has no messages")
        return 0
    for msg in messages[-n:]:
        ts = msg.time[:16].replace("T", " ") if msg.time else ""
        mentions = " ".join(f"@{m}" for m in msg.mentions)
        suffix = f"  [{mentions}]" if mentions else ""
        print(f"{ts}  {msg.author:8} {msg.text}{suffix}")

    state = load_state(name)
    if state:
        status = "running" if state.running else "stopped"
        print(f"\n[{status}, {state.turns_used}/{state.turn_cap} turns, "
              f"project: {state.primary}]")
    return 0


def cfg_primary(cfg: config.Config) -> str | None:
    """Read [room] primary from config.toml."""
    try:
        path = config.HOME / "config.toml"
        if not path.exists():
            return None
        import tomllib
        data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
        room = data.get("room", {})
        if isinstance(room, dict):
            primary = room.get("primary")
            if isinstance(primary, str) and primary.strip():
                return primary.strip()
    except (ValueError, TypeError, OSError):
        pass
    return None
