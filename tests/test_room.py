"""Tests for the Hive room engine and token-budget optimizations (B1)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from megazword import config, room
from megazword.backends import Backend, Result
from megazword.cli import main
from megazword.memory import Memory
from megazword.pacing import PlanStatus


@dataclass
class FakeBackend(Backend):
    reply: str = "ok from fake"
    available_flag: bool = True
    calls: list[str] = None

    def __post_init__(self):
        if self.calls is None:
            self.calls = []

    def available(self) -> bool:
        return self.available_flag

    def _run(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.reply


def test_append_and_read_messages(tmp_path):
    msg1 = room.append_message("testroom", "phil", "hello @claude, what is next?", home=tmp_path)
    assert msg1.author == "phil"
    assert msg1.mentions == ["claude"]
    assert "what is next" in msg1.text

    msg2 = room.append_message("testroom", "claude", "hey @codex and @grok, let's build B1.",
                               prompt_chars=1200, home=tmp_path)
    assert msg2.author == "claude"
    assert set(msg2.mentions) == {"codex", "grok"}
    assert msg2.prompt_chars == 1200

    messages = room.read_messages("testroom", home=tmp_path)
    assert len(messages) == 2
    assert messages[0].text == msg1.text
    assert messages[1].prompt_chars == 1200


def test_state_card_under_300_words(tmp_path):
    mem = Memory(tmp_path, "workshop")
    mem.add("decision", "Always check usage before and after steps.")
    mem.add("decision", "Truth only, never make things up.")
    mem.add("decision", "One AI at a time on main.")
    mem.add("note", "B1 room engine in progress.")
    mem.add("done", "Beta 1 tagged.")

    card = room.build_state_card("workshop", home=tmp_path)
    assert "Primary project: workshop" in card
    assert "Always check usage" in card
    assert "B1 room engine in progress" in card
    assert len(card.split()) < 300


def test_condense_messages():
    messages = [
        room.RoomMessage(time="2026-10-11T12:00:00Z", author="phil", text=f"Message {i} @claude")
        for i in range(10)
    ]
    summary = room.condense_messages(messages, existing_summary="Prior discussion")
    lines = summary.splitlines()
    assert len(lines) <= 5
    assert any("Message" in line for line in lines)


def test_pick_next_speaker_mentions():
    eligible = ["claude", "codex", "grok"]
    burn_order = ["grok", "codex", "claude"]

    # Explicit mention
    msg = room.RoomMessage(time="", author="phil", text="hey @codex check this", mentions=["codex"])
    speaker = room.pick_next_speaker(msg, eligible, burn_order, last_speaker="claude")
    assert speaker == "codex"

    # Mentioned bot not eligible
    msg_out = room.RoomMessage(time="", author="phil", text="hey @gemini", mentions=["gemini"])
    speaker_fallback = room.pick_next_speaker(msg_out, eligible, burn_order, last_speaker="grok")
    # Falls back to burn order avoiding last_speaker grok -> codex
    assert speaker_fallback == "codex"

    # A bot @mention must not start another one-shot (falls back to burn order)
    bot = room.RoomMessage(time="", author="codex", text="hey @grok identify", mentions=["grok"])
    speaker_bot = room.pick_next_speaker(bot, eligible, burn_order, last_speaker="grok")
    assert speaker_bot == "codex"


def test_pick_next_speaker_alternates_away_from_last_speaker():
    eligible = ["claude", "codex"]
    burn_order = ["claude", "codex"]

    # No mentions: pick burn order #0 if not last_speaker
    msg = room.RoomMessage(time="", author="system", text="starting")
    speaker1 = room.pick_next_speaker(msg, eligible, burn_order, last_speaker="codex")
    assert speaker1 == "claude"

    # Next turn: if claude just spoke, alternate to codex
    speaker2 = room.pick_next_speaker(msg, eligible, burn_order, last_speaker="claude")
    assert speaker2 == "codex"


def test_room_stop_command(tmp_path):
    room.set_stopped("stoproom", False, home=tmp_path)
    state = room.load_state("stoproom", home=tmp_path)
    assert not state.stopped

    room.stop("stoproom", home=tmp_path)
    state = room.load_state("stoproom", home=tmp_path)
    assert state.stopped


def test_save_summary_report(tmp_path):
    messages = [
        room.RoomMessage("2026-10-11T12:00:00Z", "phil", "hello"),
        room.RoomMessage("2026-10-11T12:00:05Z", "claude", "hi phil @codex"),
        room.RoomMessage("2026-10-11T12:00:10Z", "codex", "reporting in"),
    ]
    report_file = room.save_summary_report("testroom", messages, "workshop", home=tmp_path)
    assert report_file.exists()
    content = report_file.read_text(encoding="utf-8")
    assert "Hive Room Summary: testroom" in content
    assert "Primary project: workshop" in content
    assert "Participating bots: claude, codex" in content


def test_room_cli_commands(tmp_path, capsys):
    cfg = config.Config(log_path=tmp_path / "log.jsonl")
    backends = {
        "claude": FakeBackend("claude", reply="Understood @codex"),
        "codex": FakeBackend("codex", reply="Ready @claude"),
    }

    # say
    code = main(["room", "say", "hello room @claude"], backends=backends, cfg=cfg)
    assert code == 0
    out = capsys.readouterr().out
    assert "[phil] hello room @claude" in out

    # show
    code = main(["room", "show"], backends=backends, cfg=cfg)
    assert code == 0
    out = capsys.readouterr().out
    assert "hello room @claude" in out

    # start is retained only to explain that the house bot is disabled
    code = main(["room", "start", "--turns", "2"], backends=backends, cfg=cfg)
    assert code == 0
    out = capsys.readouterr().out
    assert "house bot disabled" in out
    assert "[codex] Ready @claude" not in out

    # stop
    code = main(["room", "stop"], backends=backends, cfg=cfg)
    assert code == 0
    out = capsys.readouterr().out
    assert "stopped room 'hive'" in out

    # post-summary only prints unless --post is given (and conftest blocks gh anyway)
    code = main(["room", "post-summary"], backends=backends, cfg=cfg)
    assert code in (0, 1)
    out = capsys.readouterr().out
    assert "add --post to send it" in out or "no summary found" in out


def test_post_summary_posts_only_with_post(tmp_path, monkeypatch):
    import subprocess
    from megazword import room
    calls = []
    monkeypatch.setattr(room, "_gh_path", lambda: "gh")
    monkeypatch.setattr(room.subprocess, "run", lambda cmd, **kw: calls.append(cmd)
                        or subprocess.CompletedProcess(cmd, 0, "", ""))
    path = room.summary_path("hive", tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("Highlights: ready @codex", encoding="utf-8")
    lines = []

    assert room.post_summary("hive", home=tmp_path, write=lines.append) == 0
    assert calls == []
    assert "add --post" in lines[-1]

    assert room.post_summary("hive", home=tmp_path, write=lines.append, post=True) == 0
    assert calls and calls[0][:3] == ["gh", "pr", "comment"]
    assert "@codex" not in calls[0][-1]
    assert "posted summary" in lines[-1]


def test_quiet_mentions_breaks_github_pings():
    from megazword.room import quiet_mentions
    out = quiet_mentions("hello @claude, @codex ready; mail a@b")
    assert "@claude" not in out and "@codex" not in out
    assert out.replace("​", "") == "hello @claude, @codex ready; mail a@b"


def test_parse_lessons_strips_bullets_and_caps_at_five():
    text = "Here you go:\n- Lead with usage.\n2) Keep replies short\n* x\n" + "\n".join(
        f"- lesson number {i}" for i in range(6))
    lessons = room.parse_lessons(text)
    assert lessons[:2] == ["Here you go:", "Lead with usage."] or lessons[1] == "Lead with usage."
    assert "Keep replies short" in lessons
    assert "x" not in lessons and len(lessons) == 5


def test_room_names_cannot_leave_the_rooms_folder(tmp_path):
    with pytest.raises(ValueError):
        room.room_path("../evil", tmp_path)


def test_state_survives_concurrent_saves_and_extra_keys(tmp_path):
    import threading
    state = room.load_state("hive", tmp_path)
    state.session, state.summary_pad = "me", None  # extra attribute is not a field; ignored
    room.save_state(state, tmp_path)
    path = room.state_path("hive", tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["future_field"] = 1  # a newer Mega Zword may add fields
    path.write_text(json.dumps(data), encoding="utf-8")
    assert room.load_state("hive", tmp_path).session == "me"

    bad = []
    def writer():
        for i in range(200):
            s = room.RoomState(room="hive", session="me", rolling_summary="x" * (i * 50))
            room.save_state(s, tmp_path)
    def reader():
        for _ in range(200):
            if room.load_state("hive", tmp_path).session != "me":
                bad.append(1)
    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert not bad


def test_bad_lines_in_the_room_log_are_skipped(tmp_path):
    room.append_message("messy", "phil", "first", home=tmp_path)
    with room.room_path("messy", tmp_path).open("a", encoding="utf-8") as f:
        f.write('\n5\n"just text"\n[1, 2]\n{not json\n')
    room.append_message("messy", "claude", "second", home=tmp_path)
    assert [m.text for m in room.read_messages("messy", home=tmp_path)] == ["first", "second"]


def test_broken_state_file_starts_fresh(tmp_path):
    room.say("broken", "hi", home=tmp_path)
    room.state_path("broken", tmp_path).parent.mkdir(parents=True, exist_ok=True)
    room.state_path("broken", tmp_path).write_text("{oops", encoding="utf-8")
    state = room.load_state("broken", tmp_path)
    assert state.room == "broken" and not state.stopped


def test_show_empty_room(tmp_path):
    out = []
    assert room.show("empty", home=tmp_path, write=out.append) == 0
    assert out == ["[megazword room] room 'empty' has no messages yet"]


def test_turn_prompt_has_no_mention_rule():
    """Phil, 2026-10-20: no "don't @mention other bots" rule in prompts."""
    from megazword.room import build_turn_prompt
    alone = build_turn_prompt("card", "", "phil: hi", "grok", "workshop", "phil", others=[])
    assert "answer Phil yourself" in alone and "@claude" not in alone
    two = build_turn_prompt("card", "", "phil: hi", "grok", "workshop", "phil", others=["codex"])
    assert "@codex" in two and "@claude" not in two
    legacy = build_turn_prompt("card", "", "phil: hi", "grok", "workshop", "phil")
    for text in (alone, two, legacy):
        assert "@mention" not in text
