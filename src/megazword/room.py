"""The Hive room: authenticated remote chat, local cache and durable send queue."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field, fields
import uuid
import hashlib
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from . import config, failures, log, pacing
from .backends import Backend, default_backends
from .filelock import locked, write_atomic
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
    remote_id: int = 0
    remote_url: str = ""


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
                if not isinstance(data, dict):  # e.g. a stray `5` or `"text"` line
                    continue
                messages.append(RoomMessage(
                    time=data.get("time", ""),
                    author=data.get("author", "unknown"),
                    text=data.get("text", ""),
                    mentions=data.get("mentions", []),
                    prompt_chars=data.get("prompt_chars", 0),
                    remote_id=data.get("remote_id", 0),
                    remote_url=data.get("remote_url", ""),
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
    # Read under the same lock save_state holds: a half-written file read as the default
    # state looked like "a newer session took over" and stopped a running room.
    try:
        with locked(path):
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        known = {f.name for f in fields(RoomState)}
        return RoomState(**{k: v for k, v in data.items() if k in known})
    except Exception:
        return RoomState(room=room)


def save_state(state: RoomState, home: Path | None = None) -> None:
    path = state_path(state.room, home)
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked(path):
        write_atomic(path, json.dumps(asdict(state), indent=2))


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


def release(room: str, session: str, home: Path | None = None) -> bool:
    """The host process is exiting mid-session (e.g. Phil closed the app window, which
    kills the room thread before its cleanup runs). Mark that session paused instead of
    leaving it 'active', which would refuse Start for 20 minutes. Another session's
    room is left alone."""
    state = load_state(room, home)
    if not state.active or state.session != session:
        return False
    state.active = False
    state.paused = True
    save_state(state, home)
    return True


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
    1. If Phil @mentioned eligible bots, pick the first mentioned.
       Mentions in bot/floor lines are ignored (they used to spawn extra one-shots).
    2. Otherwise, pick from burn order, alternating away from last_speaker when possible.
    3. Return None if no eligible bot exists.
    """
    if not eligible:
        return None

    if last_msg and last_msg.author == "phil" and last_msg.mentions:
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
                      reply_words: int = DEFAULT_REPLY_WORDS,
                      others: list[str] | None = None) -> str:
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

    # `others`: bots that can actually speak next. A bot's @mention never starts a
    # one-shot (pick_next_speaker ignores bot mentions), so no rule is needed here.
    if others is None:
        handoff = "Phil's live sessions read this log."
    elif others:
        handoff = ("Live seats read this log: "
                   + ", ".join(f"@{b}" for b in others) + ".")
    else:
        handoff = "You are the only one-shot in the room right now; answer Phil yourself."
    parts.append(
        f"[Your Turn: @{speaker}]\n"
        f"{lead_in} Keep your answer friendly, concise, and under {reply_words} words. "
        f"Never write code or edit files here; do that in normal tasks. "
        f"{handoff}"
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
             home: Path | None = None,
             session: str | None = None) -> int:
    """Compatibility entry point: the room no longer launches one-shot house bots."""
    write("[megazword room] house bot disabled; real seats use room say/show")
    return 0


def check_author(author: str) -> None:
    """Only Phil posts as phil: a bot seat ($MEGAZWORD_SEAT set to anything else) can't (B7)."""
    seat = (os.environ.get("MEGAZWORD_SEAT") or "").strip().lower()
    if author.strip().lower() == "phil" and seat not in ("", "phil"):
        raise PermissionError(f"seat '{seat}' cannot post as phil")


def safe_write(write: Callable[[str], None], text: str) -> None:
    """Windows redirected cp1252 consoles cannot represent every room character."""
    try:
        write(text)
    except UnicodeEncodeError as exc:
        write(text.encode(exc.encoding, errors="replace").decode(exc.encoding))


# Statuses that mean "this post will never be accepted": bad request, claim conflict,
# too large, invalid. Auth (401/403), rate limits (429) and 5xx stay queued for retry.
REJECTED = frozenset({400, 409, 413, 422})


class RemoteRoom:
    def __init__(self, room: str, cfg: config.Config, home: Path | None):
        from .keys import get_key
        self.rejected: list[str] = []
        self.url = (os.environ.get("HIVE_ROOM_URL") or cfg.room_url).rstrip("/")
        parsed = urlsplit(self.url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
            raise ValueError("room URL must be an HTTPS origin without credentials, path or query")
        if not re.fullmatch(r"[a-z0-9-]{1,64}", room):
            raise ValueError("remote room names use lowercase a-z, digits and - (1-64 characters)")
        # Prefer this seat's own lane key so posts carry the real designation;
        # fall back to the shared HIVE_ROOM_TOKEN (all PC seats share one slot today).
        seat = (os.environ.get("MEGAZWORD_SEAT") or "").strip()
        own = get_key("HIVE_ROOM_KEY_" + seat.replace("-", "_").upper()) if seat else None
        self.token = own or get_key("HIVE_ROOM_TOKEN")
        if not self.token:
            raise ValueError("HIVE_ROOM_TOKEN missing: set it in Keymaster or environment secrets")
        self.room, self.home = room, home
        self.endpoint = f"{self.url}/rooms/{room}/messages"
        # A queue belongs to one origin and credential; never replay it as a different seat.
        binding = hashlib.sha256((self.url + "\0" + self.token).encode()).hexdigest()[:24]
        self.queue = room_dir(home) / f"{room}.{binding}.queue.json"

    def request(self, method: str, suffix: str = "", item: dict | None = None) -> dict:
        # Cloudflare answers Python's default User-Agent with 403 (error 1010), so name ourselves.
        headers = {"Authorization": "Bearer " + self.token, "Content-Type": "application/json",
                   "User-Agent": "megazword-room/1"}
        data = None
        if item is not None:
            headers["Idempotency-Key"] = item["id"]
            data = json.dumps({"text": item["text"]}).encode("utf-8")
        req = urllib.request.Request(self.endpoint + suffix, data=data, headers=headers, method=method)
        # Never forward a seat token to a redirect target.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=10) as response:
            return json.load(response)

    def cached(self) -> list[RoomMessage]:
        return [m for m in read_messages(self.room, self.home) if m.remote_url == self.url]

    def cache(self, rows: list[dict]) -> None:
        path = room_path(self.room, self.home)
        with locked(path) as acquired:
            if not acquired:
                raise OSError("cache busy")
            # read_messages uses the same sidecar lock, so read directly while holding it.
            raw = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
            records = [json.loads(line) for line in raw if line.strip()]
            known = {r.get("remote_id") for r in records if r.get("remote_url") == self.url}
            for row in rows:
                if (not isinstance(row, dict) or type(row.get("id")) is not int or row["id"] < 1
                        or not all(isinstance(row.get(k), str) for k in ("author", "text", "time"))):
                    raise ValueError("invalid server message")
                if row["id"] not in known:
                    records.append(asdict(RoomMessage(row["time"], row["author"], row["text"],
                        extract_mentions(row["text"]), remote_id=row["id"], remote_url=self.url)))
                    known.add(row["id"])
            records.sort(key=lambda r: r.get("remote_id", 0))
            write_atomic(path, "".join(json.dumps(r) + "\n" for r in records))

    def flush(self, text: str | None = None) -> int:
        with locked(self.queue) as acquired:
            if not acquired:
                raise OSError("send queue busy; message not queued")
            pending = json.loads(self.queue.read_text(encoding="utf-8")) if self.queue.exists() else []
            if text is not None:
                pending.append({"id": uuid.uuid4().hex, "text": text})
                write_atomic(self.queue, json.dumps(pending))  # durable before any network call
            while pending:
                try:
                    message = self.request("POST", item=pending[0])["message"]
                    self.cache([message])
                except urllib.error.HTTPError as exc:
                    if exc.code not in REJECTED:
                        break  # outage, auth or rate limit: keep it and retry later
                    # The server refused this post and always will. Kept at the head it
                    # blocked every later post from the seat (2026-10-21: 13:06 to 20:07,
                    # behind one 409), so set it aside with the reason instead.
                    self.reject(pending[0], exc)
                except (OSError, ValueError, KeyError, TypeError):
                    break  # keep the item on every other HTTP/storage/validation failure
                pending.pop(0)
                write_atomic(self.queue, json.dumps(pending))
            return len(pending)

    def reject(self, item: dict, exc: urllib.error.HTTPError) -> None:
        try:
            reason = json.loads(exc.read() or b"{}").get("error", "")
        except (OSError, ValueError, AttributeError):
            reason = ""
        reason = str(reason or exc.reason or "")[:300]
        path = self.queue.with_suffix(".rejected.json")
        try:
            kept = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        except (OSError, ValueError):
            kept = []
        kept.append({**item, "status": exc.code, "error": reason})
        write_atomic(path, json.dumps(kept))
        self.rejected.append(f"HTTP {exc.code}: {reason}" if reason else f"HTTP {exc.code}")

    def refresh(self) -> None:
        # Start from the last contiguous GET cursor, not a POST's potentially later ID.
        cursor_path = self.queue.with_suffix(".cursor.json")
        with locked(cursor_path) as acquired:
            if not acquired:
                raise OSError("room refresh busy")
            since = int(cursor_path.read_text(encoding="utf-8")) if cursor_path.exists() else 0
            while True:
                rows = self.request("GET", f"?since={since}&limit=200")["messages"]
                self.cache(rows)
                if not rows:
                    break
                next_id = rows[-1]["id"]
                if next_id <= since:
                    raise ValueError("invalid server cursor")
                since = next_id
                write_atomic(cursor_path, str(since))
                if len(rows) < 200:
                    break


def report_rejected(client: RemoteRoom, write: Callable[[str], None]) -> None:
    for reason in client.rejected:
        safe_write(write, f"[megazword room] the room refused a queued post ({reason}); "
                          f"it was set aside in {client.queue.with_suffix('.rejected.json').name}")


def remote_configured(cfg: config.Config) -> bool:
    return bool(os.environ.get("HIVE_ROOM_URL") or cfg.room_url)


def say(room: str, text: str, author: str = "phil",
        home: Path | None = None, write: Callable[[str], None] = print,
        cfg: config.Config | None = None, force: bool = False) -> int:
    """Post as the authenticated seat, or append locally when no URL is configured."""
    cfg = cfg or config.load()
    if not text.strip() or len(text) > 4000:
        raise ValueError("message must contain 1-4000 characters")
    from .claims import active_claims, claim_from_text, item_keys, unkeyed_claim
    claim = claim_from_text(text)
    if not force and unkeyed_claim(text):
        safe_write(write, "[megazword room] a claim must name its item as #N or a quoted "
                   "'name' so other seats can check it, e.g. \"Name-19: claiming 'claim lock'\"")
        return 1
    if claim and not force:
        try:
            opened = active_claims(claim_messages(room, cfg, home), now=datetime.now(timezone.utc))
        except (OSError, ValueError, KeyError, TypeError):
            opened = {}  # A failed read must never prevent posting.
        for designation, (item, _, _) in opened.items():
            if designation.lower() == claim[0].lower() or item_keys(item) & item_keys(claim[1]):
                safe_write(write, f"[megazword room] {designation} has open claim '{item}'; "
                           f"post '{designation}: releasing {item}' first (or use --force)")
                return 1
    if remote_configured(cfg):
        client = RemoteRoom(room, cfg, home)
        pending = client.flush(text)
        report_rejected(client, write)
        safe_write(write, f"[megazword room] {pending} queued; retry on next say/show" if pending else "[megazword room] sent as the authenticated seat")
    else:
        check_author(author)
        msg = append_message(room, author, text, home=home)
        safe_write(write, f"[{msg.author}] {msg.text}")
    if claim and not force:
        return _lost_race(room, claim, cfg, home, write)
    return 0


def _lost_race(room: str, claim: tuple[str, str], cfg: config.Config,
               home: Path | None, write: Callable[[str], None]) -> int:
    """Two seats can pass the check seconds apart. Re-read: the earliest open claim
    on the item wins and a later one releases itself, so only one seat works on it."""
    from .claims import first_holder
    try:
        holder = first_holder(claim_messages(room, cfg, home), *claim)
    except (OSError, ValueError, KeyError, TypeError):
        return 0
    if not holder:
        return 0
    # No item key in the release, so it frees only this seat's claim, not the winner's.
    say(room, f"{claim[0]}: releasing my claim; {holder} claimed it first.",
        home=home, write=lambda _s: None, cfg=cfg, force=True)
    safe_write(write, f"[megazword room] {holder} claimed it first; your claim was released. Pick another item.")
    return 1


def claim_messages(room: str, cfg: config.Config, home: Path | None = None) -> list[RoomMessage]:
    """Refresh once and use the existing cache; propagate read errors to the caller."""
    if remote_configured(cfg):
        client = RemoteRoom(room, cfg, home)
        client.refresh()
        return client.cached()
    return read_messages(room, home)


def show_claims(room: str, home: Path | None = None,
                write: Callable[[str], None] = print, cfg: config.Config | None = None) -> int:
    from .claims import active_claims, claim_conflicts
    try:
        opened = active_claims(claim_messages(room, cfg or config.load(), home),
                               now=datetime.now(timezone.utc))
    except (OSError, ValueError, KeyError, TypeError):
        safe_write(write, "[megazword room] claims unavailable; room could not be read")
        return 1
    for designation, (item, message_id, time) in opened.items():
        safe_write(write, f"{designation}: {item} (message {message_id}, {time})")
    for first, second, number in claim_conflicts(opened):
        label = f"#{number}" if isinstance(number, int) else f"'{number}'"
        safe_write(write, f"Conflict: {first} and {second} both claim {label}")
    if not opened:
        safe_write(write, "[megazword room] no active claims")
    return 0


def show_kinds(room: str, n: int = 50, home: Path | None = None,
               write: Callable[[str], None] = print, cfg: config.Config | None = None) -> int:
    """One block per seat: what it claimed, finished, or is blocked on.

    This is the reader's view of the room. Reading the raw log means scrolling 200 lines to
    learn that one seat is blocked; this says it in one line. No model call, no judgement -
    the labels come from the text the seats already write.
    """
    from .claims import render_kinds, summarize_kinds
    try:
        messages = claim_messages(room, cfg or config.load(), home)
    except (OSError, ValueError, KeyError, TypeError):
        safe_write(write, "[megazword room] kinds unavailable; room could not be read")
        return 1
    safe_write(write, render_kinds(summarize_kinds(messages[-n:] if n > 0 else messages)))
    return 0


def show(room: str, n: int = 20, home: Path | None = None,
         write: Callable[[str], None] = print, cfg: config.Config | None = None) -> int:
    """Show recent messages from the room."""
    if n < 1:
        raise ValueError("message count must be positive")
    cfg = cfg or config.load()
    if remote_configured(cfg):
        # Credential failures must not look like a successful local post/read.
        client = RemoteRoom(room, cfg, home)
        pending = client.flush()
        report_rejected(client, write)
        if pending:
            safe_write(write, f"[megazword room] {pending} messages still queued; retry on next say/show")
        try:
            client.refresh()
        except (OSError, ValueError, KeyError, TypeError):
            safe_write(write, "[megazword room] remote unavailable; showing local cache")
        messages = client.cached()
    else:
        messages = read_messages(room, home)
    if not messages:
        safe_write(write, f"[megazword room] room '{room}' has no messages yet")
        return 0
    for m in messages[-n:]:
        mentions = f" (mentions: {', '.join(m.mentions)})" if m.mentions else ""
        safe_write(write, f"{m.time[:16]} [{m.author}]{mentions}: {m.text}")
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
            from .backends import no_window
            res = subprocess.run([gh, "pr", "comment", "33", "--repo", "edotwedo/workshop", "--body", content],
                                 capture_output=True, text=True, timeout=15, **no_window())
            if res.returncode == 0:
                write(f"[megazword room] posted summary for '{room}' to Q (PR #33)")
                return 0
        except Exception:
            pass

    hint = "" if post else " (add --post to send it)"
    write(f"[megazword room] summary for '{room}' (paste to Q PR #33{hint}):\n\n{content}")
    return 0
