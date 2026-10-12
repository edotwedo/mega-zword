"""The Hive room: bot group chat with token-budget optimizations."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from . import config, failures, log, pacing
from .backends import Backend, default_backends
from .filelock import locked
from .memory import Memory, project_name

DEFAULT_ROOM = "hive"
DEFAULT_TURN_CAP = 12
DEFAULT_REPLY_WORDS = 80
RECENT_MESSAGES_COUNT = 4
SUMMARY_EVERY = 6
KNOWN_BOTS = ("claude", "codex", "grok", "gemini")


@dataclass
class RoomMessage:
    time: str
    author: str
    text: str
    mentions: list[str] = field(default_factory=list)
    prompt_chars: int = 0


@dataclass
class RoomState:
    room: str = DEFAULT_ROOM
    active: bool = False
    stopped: bool = False
    paused: bool = False
    turn_count: int = 0
    turn_cap: int = DEFAULT_TURN_CAP
    primary: str = "workshop"
    last_speaker: str | None = None
    rolling_summary: str = ""
    summarized_count: int = 0
    # One running session per room (B1 second look, Tally-11): its id and last sign of life.
    session: str = ""
    heartbeat: str = ""


STALE_AFTER = timedelta(minutes=20)  # longer than one slow turn (the CLI timeout is 10 min)


def _valid_room(room: str) -> str:
    if not room or not all(c.isalnum() or c in "-_" for c in room):
        raise ValueError(f"room name {room!r}: use letters, digits, - and _")
    return room


def other_session_running(state: RoomState, now: datetime | None = None) -> bool:
    if not state.active or not state.heartbeat:
        return False
    try:
        beat = datetime.fromisoformat(state.heartbeat)
    except ValueError:
        return False
    return (now or datetime.now(timezone.utc)) - beat < STALE_AFTER


def room_dir(home: Path | None = None) -> Path:
    return (home or config.HOME) / "rooms"


def room_path(room: str = DEFAULT_ROOM, home: Path | None = None) -> Path:
    return room_dir(home) / f"{_valid_room(room)}.jsonl"


def state_path(room: str = DEFAULT_ROOM, home: Path | None = None) -> Path:
    return room_dir(home) / f"{_valid_room(room)}.state.json"


def summary_dir(home: Path | None = None) -> Path:
    return room_dir(home) / "summaries"


def summary_path(room: str = DEFAULT_ROOM, home: Path | None = None) -> Path:
    return summary_dir(home) / f"{room}.txt"


def extract_mentions(text: str) -> list[str]:
    """Find @mentions in message text, returned as lowercase bot names."""
    found = re.findall(r"@([A-Za-z0-9_-]+)", text)
    mentions = []
    for name in found:
        low = name.lower()
        if low in KNOWN_BOTS and low not in mentions:
            mentions.append(low)
    return mentions


def read_messages(room: str = DEFAULT_ROOM, home: Path | None = None) -> list[RoomMessage]:
    path = room_path(room, home)
    if not path.exists():
        return []
    messages = []
    with locked(path):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                messages.append(RoomMessage(
                    time=data.get("time", ""),
                    author=data.get("author", "unknown"),
                    text=data.get("text", ""),
                    mentions=data.get("mentions", []),
                    prompt_chars=data.get("prompt_chars", 0),
                ))
            except (json.JSONDecodeError, TypeError):
                continue
    return messages


def append_message(room: str, author: str, text: str,
                   prompt_chars: int = 0, home: Path | None = None,
                   when: str | None = None) -> RoomMessage:
    path = room_path(room, home)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = when or datetime.now(timezone.utc).isoformat(timespec="seconds")
    mentions = extract_mentions(text)
    msg = RoomMessage(
        time=stamp,
        author=author.lower(),
        text=text.strip(),
        mentions=mentions,
        prompt_chars=prompt_chars,
    )
    with locked(path):
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(msg)) + "\n")
    return msg


def load_state(room: str = DEFAULT_ROOM, home: Path | None = None) -> RoomState:
    path = state_path(room, home)
    if not path.exists():
        return RoomState(room=room)
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        return RoomState(**data)
    except Exception:
        return RoomState(room=room)


def save_state(state: RoomState, home: Path | None = None) -> None:
    path = state_path(state.room, home)
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked(path):
        path.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")


def set_stopped(room: str = DEFAULT_ROOM, stopped: bool = True, home: Path | None = None) -> None:
    state = load_state(room, home)
    state.stopped = stopped
    if stopped:
        state.active = False
        state.paused = False
    save_state(state, home)


def set_paused(room: str = DEFAULT_ROOM, paused: bool = True, home: Path | None = None) -> None:
    """Ask a running room to pause after its current bot reply."""
    state = load_state(room, home)
    state.paused = paused
    save_state(state, home)


def _clip_text(text: str, max_chars: int = 150) -> str:
    return text if len(text) <= max_chars else text[:max_chars - 3].rstrip() + "..."


def build_state_card(project: str, home: Path | None = None) -> str:
    """Concise state card (<300 words): primary project, in progress, last 3 decisions, schedule."""
    mem = Memory(home or config.HOME, project)
    entries = mem.entries()
    decisions = [e for e in entries if e.kind == "decision"][-3:]
    in_progress = [e for e in entries if e.kind in ("note", "done")][-3:]
    lessons = [e for e in entries if e.kind == "lesson"][-3:]

    lines = [
        f"[Hive State Card: {project}]",
        f"Primary project: {project}",
    ]
    if decisions:
        lines.append("Decisions to follow:")
        for d in decisions:
            lines.append(f"- {_clip_text(d.text)}")
    else:
        lines.append("Decisions: none recorded yet.")

    if in_progress:
        lines.append("In progress / recent:")
        for item in in_progress:
            lines.append(f"- {item.by}: {_clip_text(item.text)}")
    else:
        lines.append("In progress: none recorded yet.")

    if lessons:
        lines.append("Lessons from earlier sessions:")
        for item in lessons:
            lines.append(f"- {_clip_text(item.text, 120)}")

    lines.append("Today's schedule: none")
    card = "\n".join(lines)
    # Ensure word count is strictly bounded
    words = card.split()
    if len(words) > 280:
        card = " ".join(words[:280]) + "..."
    return card


def condense_messages(messages: list[RoomMessage], existing_summary: str = "") -> str:
    """Condense older messages into a 5-line rolling summary."""
    if not messages:
        return existing_summary
    recent_take = messages[-8:]
    summary_lines = []
    if existing_summary:
        summary_lines.append(existing_summary.splitlines()[0])
    for m in recent_take:
        summary_lines.append(f"- {m.author}: {_clip_text(m.text, 80)}")
    return "\n".join(summary_lines[-5:])


def get_eligible_backends(backends: dict[str, Backend], cfg: config.Config,
                          statuses: dict | None = None) -> dict[str, Backend]:
    """Filter backends to those installed, not marked out, and not out/over-pace."""
    out_now = cfg.out_now()
    eligible: dict[str, Backend] = {}
    for name, b in backends.items():
        if name not in KNOWN_BOTS:
            continue
        if not b.available():
            continue
        if name in out_now:
            continue
        if statuses:
            st = statuses.get(name)
            if st and getattr(st, "verdict", "unknown") in ("out", "hard-only"):
                continue
        eligible[name] = b
    return eligible


def get_burn_order(eligible: dict[str, Backend], statuses: dict | None = None) -> list[str]:
    """Rank eligible bots by pacing burn rule (easy difficulty)."""
    return pacing.rank(statuses or {}, list(eligible.keys()), "easy")


def pick_next_speaker(last_msg: RoomMessage | None, eligible: list[str],
                      burn_order: list[str], last_speaker: str | None = None) -> str | None:
    """Pick the next AI to speak:
    1. If the last message @mentioned eligible bots, pick the first mentioned.
    2. Otherwise, pick from burn order, alternating away from last_speaker when possible.
    3. Return None if no eligible bot exists.
    """
    if not eligible:
        return None

    if last_msg and last_msg.mentions:
        for m in last_msg.mentions:
            if m in eligible:
                return m

    # No mentions or mentioned bot not eligible: pick next in burn order
    candidates = [b for b in burn_order if b in eligible]
    if not candidates:
        candidates = eligible

    # Avoid immediate self-response if another bot is eligible
    if len(candidates) > 1 and last_speaker and candidates[0] == last_speaker:
        return candidates[1]
    return candidates[0]


def format_recent(messages: list[RoomMessage], count: int = RECENT_MESSAGES_COUNT) -> str:
    recent = messages[-count:]
    if not recent:
        return "(no messages yet in the room)"
    return "\n".join(f"{m.author}: {m.text}" for m in recent)


def build_turn_prompt(state_card: str, rolling_summary: str,
                      recent_text: str, speaker: str,
                      primary_project: str, last_author: str | None = None,
                      reply_words: int = DEFAULT_REPLY_WORDS) -> str:
    """Build lean turn prompt with prime directive, token budget, and reply constraints."""
    parts = [
        "[Sent by Mega Zword as a one-shot task. Answer it directly. Skip session startup, coordination and check-in routines.]",
        state_card,
    ]
    if rolling_summary:
        parts.append(f"[Earlier room summary]\n{rolling_summary}")

    parts.append(f"[Recent room conversation]\n{recent_text}")

    parts.append(
        f"[Prime Directive]\n"
        f"Work on the primary project: '{primary_project}'. Use spare plan usage that would otherwise go to waste. "
        f"Keep getting better from what worked. Phil's messages always take priority."
    )

    lead_in = (f"Phil just spoke. Address Phil's message as @{speaker}."
               if last_author == "phil" else
               f"Reply as @{speaker}.")

    parts.append(
        f"[Your Turn: @{speaker}]\n"
        f"{lead_in} Keep your answer friendly, concise, and under {reply_words} words. "
        f"Never write code or edit files here; do that in normal tasks. "
        f"Mention another bot (@claude, @codex, @grok, @gemini) to hand off or ask a question."
    )
    return "\n\n".join(parts)


def run_speaker(speaker: str, backend: Backend, prompt: str,
                session_active: bool = False) -> tuple[str, bool, float, str]:
    """Execute a room turn as a fresh one-shot."""
    # Session reuse is off: `claude --continue`, `agy --continue` and `codex exec resume`
    # pick up the most recent conversation in the folder, which can be Phil's own chat
    # (Easel-11 review, 2026-10-11). Turn it back on only with an explicit session id.
    res = backend.run(prompt)
    return res.text.strip(), res.ok, res.seconds, res.error


def save_summary_report(room: str, messages: list[RoomMessage],
                        project: str, home: Path | None = None) -> Path:
    """Save 5-10 line session summary to ~/.megazword/rooms/summaries/<room>.txt."""
    dir_path = summary_dir(home)
    dir_path.mkdir(parents=True, exist_ok=True)
    out_path = summary_path(room, home)

    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    speakers = sorted({m.author for m in messages if m.author != "phil"})
    phil_msgs = sum(1 for m in messages if m.author == "phil")

    lines = [
        f"Hive Room Summary: {room} ({stamp})",
        f"Primary project: {project}",
        f"Total messages: {len(messages)} (Phil: {phil_msgs}, Bots: {len(messages) - phil_msgs})",
        f"Participating bots: {', '.join(speakers) if speakers else 'none'}",
        "Highlights:",
    ]
    recent = messages[-5:]
    for m in recent:
        lines.append(f"- {m.author}: {_clip_text(m.text, 90)}")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


LESSON_MIN_TURNS = 3  # shorter sessions don't teach enough to pay for the extra call
MAX_LESSONS = 5


def parse_lessons(text: str) -> list[str]:
    """Pull up to MAX_LESSONS one-line lessons out of a bot's answer."""
    lessons = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
        if len(line) >= 8:
            lessons.append(_clip_text(line, 160))
    return lessons[:MAX_LESSONS]


def write_lessons(messages: list[RoomMessage], primary: str, speaker: str, backend: Backend,
                  cfg: config.Config, room: str, home: Path | None = None) -> list[str]:
    """B2: one cheap call at the end of a session saves 3-5 lessons to the project's memory,
    which the next session's state card shows. Best effort; a failure saves nothing."""
    prompt = "\n\n".join([
        "[Sent by Mega Zword as a one-shot task. Answer it directly. Skip session startup, coordination and check-in routines.]",
        f"[Room conversation, project '{primary}']\n{format_recent(messages, RECENT_MESSAGES_COUNT)}",
        "List 3 to 5 short lessons from this conversation: what worked and what to do differently "
        "next time. One per line, starting with '- ', each under 20 words. No names of people, "
        "no secrets, nothing else.",
    ])
    res = backend.run(prompt)
    log.append(cfg.log_path, cfg.log_lines, backend=speaker, forced=False, project=primary,
               room=room, lessons=True, seconds=round(res.seconds, 2), ok=res.ok, prompt_chars=len(prompt),
               answer_chars=len(res.text or ""), est_tokens=(len(prompt) + len(res.text or "")) // 4)
    if not res.ok:
        return []
    lessons = parse_lessons(res.text or "")
    mem = Memory(home or config.HOME, primary)
    for text in lessons:
        mem.add("lesson", text, by=speaker)
    return lessons


def run_room(room: str = DEFAULT_ROOM,
             max_turns: int | None = None,
             project: str | None = None,
             backends: dict[str, Backend] | None = None,
             cfg: config.Config | None = None,
             statuses: Callable[[], dict] | None = None,
             write: Callable[[str], None] = print,
             home: Path | None = None) -> int:
    """Run the room turn loop with token budgeting and guardrails."""
    cfg = cfg or config.load()
    primary = project or cfg.room_primary or project_name()
    backends = backends or default_backends(edit=False, free_models=cfg.free, lean=cfg.lean)

    state = load_state(room, home)
    if other_session_running(state):
        write(f"[megazword room] room '{room}' is already running in another window; "
              "`megazword room stop` ends it")
        return 1
    me = uuid.uuid4().hex
    state.session = me
    state.heartbeat = datetime.now(timezone.utc).isoformat(timespec="seconds")
    resuming = state.paused
    if not resuming:
        state.turn_count = 0
    state.primary = primary
    state.active = True
    state.stopped = False
    state.paused = False
    turn_cap = max_turns if max_turns is not None else cfg.room_turn_cap
    state.turn_cap = turn_cap
    save_state(state, home)

    write(f"[megazword room] started room '{room}' for project '{primary}' (turn cap: {turn_cap})")

    turns_taken = state.turn_count if resuming else 0
    session_active: dict[str, bool] = {name: False for name in backends}

    try:
        while turns_taken < turn_cap:
            state = load_state(room, home)
            if state.stopped:
                write(f"[megazword room] session stopped on command")
                break
            if state.session != me:  # stopped and restarted elsewhere: the newer one wins
                write("[megazword room] a newer session took over this room; stopping")
                break
            if state.paused:
                write("[megazword room] paused after current reply")
                break
            state.heartbeat = datetime.now(timezone.utc).isoformat(timespec="seconds")

            messages = read_messages(room, home)
            last_msg = messages[-1] if messages else None

            # Guard rail: check eligible AIs
            cur_statuses = (statuses or (lambda: {}))()
            eligible = get_eligible_backends(backends, cfg, cur_statuses)
            if not eligible:
                write("[megazword room] stopped early: all AIs are out of usage or over pace")
                break

            burn_order = get_burn_order(eligible, cur_statuses)
            speaker = pick_next_speaker(last_msg, list(eligible.keys()), burn_order, state.last_speaker)
            if not speaker:
                write("[megazword room] stopped early: no eligible AI to speak next")
                break

            # Token budget: rolling summary check
            if len(messages) > RECENT_MESSAGES_COUNT and (len(messages) - state.summarized_count) >= SUMMARY_EVERY:
                older = messages[:-RECENT_MESSAGES_COUNT]
                state.rolling_summary = condense_messages(older, state.rolling_summary)
                state.summarized_count = len(messages)
                save_state(state, home)

            # Build token-budgeted prompt
            card = build_state_card(primary, home)
            recent_text = format_recent(messages, RECENT_MESSAGES_COUNT)
            prompt = build_turn_prompt(
                card, state.rolling_summary, recent_text,
                speaker, primary, last_msg.author if last_msg else None
            )
            prompt_chars = len(prompt)

            # Execute turn
            backend = eligible[speaker]
            text, ok, seconds, err = run_speaker(speaker, backend, prompt, session_active[speaker])
            if not ok:
                write(f"[megazword room] {speaker} failed: {err}")
                # Mark session inactive on failure
                session_active[speaker] = False
                break

            session_active[speaker] = True

            # Save message
            appended = append_message(room, speaker, text, prompt_chars=prompt_chars, home=home)
            turns_taken += 1
            # Reload: a Pause, Stop or newer session may have changed the state during the turn.
            state = load_state(room, home)
            if state.session == me:
                state.turn_count += 1
                state.last_speaker = speaker
                state.heartbeat = datetime.now(timezone.utc).isoformat(timespec="seconds")
                save_state(state, home)

            # Log to run log
            log.append(
                cfg.log_path, cfg.log_lines,
                backend=speaker, forced=False, project=primary,
                room=room, seconds=round(seconds, 2), ok=True,
                prompt_chars=prompt_chars, answer_chars=len(text),
                est_tokens=(prompt_chars + len(text)) // 4
            )

            write(f"[{speaker}] {text}")

        final = load_state(room, home)
        if turns_taken >= LESSON_MIN_TURNS and final.session == me and not final.paused:
            cur_statuses = (statuses or (lambda: {}))()
            eligible = get_eligible_backends(backends, cfg, cur_statuses)
            order = get_burn_order(eligible, cur_statuses)
            if order:
                saved = write_lessons(read_messages(room, home), primary, order[0],
                                      eligible[order[0]], cfg, room, home)
                if saved:
                    write(f"[megazword room] saved {len(saved)} lessons to '{primary}' memory")

    except KeyboardInterrupt:
        write("\n[megazword room] paused/interrupted by user")
    finally:
        messages = read_messages(room, home)
        save_summary_report(room, messages, primary, home)
        state = load_state(room, home)
        if state.session == me:  # don't mark a newer session's room idle
            state.active = False
            save_state(state, home)
        write(f"[megazword room] session finished ({turns_taken} turns)")

    return 0


def say(room: str, text: str, author: str = "phil",
        home: Path | None = None, write: Callable[[str], None] = print) -> int:
    """Post a message to the room. It doesn't clear a stop: a message typed after Stop
    must not restart a session that is still finishing its turn (`room start` does that)."""
    msg = append_message(room, author, text, home=home)
    write(f"[{msg.author}] {msg.text}")
    return 0


def show(room: str, n: int = 20, home: Path | None = None,
         write: Callable[[str], None] = print) -> int:
    """Show recent messages from the room."""
    messages = read_messages(room, home)
    if not messages:
        write(f"[megazword room] room '{room}' has no messages yet")
        return 0
    for m in messages[-n:]:
        mentions = f" (mentions: {', '.join(m.mentions)})" if m.mentions else ""
        write(f"{m.time[:16]} [{m.author}]{mentions}: {m.text}")
    return 0


def stop(room: str, home: Path | None = None,
         write: Callable[[str], None] = print) -> int:
    """Stop active session in this room."""
    set_stopped(room, True, home)
    write(f"[megazword room] stopped room '{room}'")
    return 0


def quiet_mentions(text: str) -> str:
    """Break @names so a summary posted to GitHub doesn't ping real bots or people
    (a room summary with @codex woke the Codex connector on 2026-10-12)."""
    return re.sub(r"@(?=[A-Za-z0-9_-])", "@​", text)


def _gh_path() -> str | None:
    """The real GitHub CLI; tests replace this so they can never post to Q."""
    return shutil.which("gh")


def post_summary(room: str, home: Path | None = None,
                 write: Callable[[str], None] = print, post: bool = False) -> int:
    """Print the session summary; with post=True (`--post`) also post it to Q (workshop PR #33).
    Posting is opt-in: a test run posted about 12 fake summaries to Q on 2026-10-12."""
    path = summary_path(room, home)
    if not path.exists():
        write(f"[megazword room] no summary found at {path}")
        return 1
    content = quiet_mentions(path.read_text(encoding="utf-8"))
    gh = _gh_path() if post else None
    if gh:
        try:
            res = subprocess.run([gh, "pr", "comment", "33", "--repo", "edotwedo/workshop", "--body", content],
                                 capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                write(f"[megazword room] posted summary for '{room}' to Q (PR #33)")
                return 0
        except Exception:
            pass

    hint = "" if post else " (add --post to send it)"
    write(f"[megazword room] summary for '{room}' (paste to Q PR #33{hint}):\n\n{content}")
    return 0
