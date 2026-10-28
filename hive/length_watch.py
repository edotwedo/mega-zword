"""Length watch (Phil, 2026-10-28): a Claude Code UserPromptSubmit hook.

It measures the conversation for real, from the transcript Claude Code hands every hook,
counting only what is still in context (everything after the last compaction).
- yellow: the bot gets nervous in character;
- red: the bot writes its handoff now, before it is squeezed;
- a long message from Phil, or every Nth message, prompts a one-line chatty check.
Each warning fires once per level per compaction. Internal Hive tool: never shipped.
Numbers live in ~/.megazword/config.toml under [hive.length_watch]."""

import json
import sys
import tomllib
from pathlib import Path

DEFAULTS = {
    "yellow_chars": 400_000,
    "red_chars": 600_000,
    "long_prompt_chars": 1_500,
    "chat_check_every": 10,
}
COUNTED = {"user", "assistant", "attachment"}

YELLOW = ("LENGTH WATCH yellow: this conversation holds about {chars:,} characters since the last "
          "compaction (roughly {pct}% of a ~800k window). Per DECISIONS 2026-10-28, mention it to "
          "Phil in character, nervous, in one line, and keep working.")
RED = ("LENGTH WATCH red: about {chars:,} characters ({pct}%). Write your handoff or memory packet "
       "NOW (handoffs/TEMPLATE.md), tell Phil in character in one line, then continue.")
CHATTY = ("CHATTY CHECK: {why}. If Phil's recent messages are mostly side ideas rather than work, "
          "nudge him once in one friendly line and offer to fork it off as a handoff "
          "(DECISIONS 2026-10-28). If they were work, say nothing about this.")


def home() -> Path:
    return Path.home() / ".megazword"


def settings() -> dict:
    try:
        data = tomllib.loads((home() / "config.toml").read_text(encoding="utf-8"))
        own = data.get("hive", {}).get("length_watch", {})
    except (OSError, ValueError):
        own = {}
    return {k: int(own.get(k, v)) for k, v in DEFAULTS.items()}


def text_size(value) -> int:
    if isinstance(value, str):
        return len(value)
    if isinstance(value, list):
        return sum(text_size(v) for v in value)
    if isinstance(value, dict):
        return sum(text_size(v) for k, v in value.items() if k in ("text", "content", "input", "message"))
    return 0


def measure(transcript: Path) -> tuple[int, str]:
    """Characters in context since the last compaction, and that compaction's id."""
    chars, era = 0, "start"
    with transcript.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("type") == "system" and entry.get("subtype") == "compact_boundary":
                chars, era = 0, entry.get("uuid", "compact")
            elif entry.get("type") in COUNTED:
                chars += text_size(entry.get("message") or entry.get("attachment") or "")
    return chars, era


def check(event: dict, cfg: dict, state: dict) -> list[str]:
    notes = []
    path = event.get("transcript_path")
    if path and Path(path).is_file():
        chars, era = measure(Path(path))
        if state.get("era") != era:
            state.update(era=era, fired=[])
        pct = round(chars * 100 / 800_000)
        for level, limit, text in (("red", cfg["red_chars"], RED), ("yellow", cfg["yellow_chars"], YELLOW)):
            if chars >= limit:
                if level not in state["fired"]:
                    state["fired"] += ["yellow", "red"] if level == "red" else ["yellow"]
                    notes.append(text.format(chars=chars, pct=pct))
                break
    state["prompts"] = state.get("prompts", 0) + 1
    prompt = event.get("prompt") or ""
    if len(prompt) > cfg["long_prompt_chars"]:
        notes.append(CHATTY.format(why=f"Phil's last message is {len(prompt):,} characters"))
    elif cfg["chat_check_every"] and state["prompts"] % cfg["chat_check_every"] == 0:
        notes.append(CHATTY.format(why=f"Phil has sent {state['prompts']} messages this session"))
    return notes


def main() -> None:
    event = json.loads(sys.stdin.read() or "{}")
    session = "".join(c for c in event.get("session_id", "none") if c.isalnum() or c in "-_") or "none"
    store = home() / "hive" / "length_watch" / f"{session}.json"
    try:
        state = json.loads(store.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    state.setdefault("fired", [])
    notes = check(event, settings(), state)
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(json.dumps(state), encoding="utf-8")
    if notes:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                 "additionalContext": "\n".join(notes)}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # a broken hook must never block Phil's session
        pass
