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


def test_guard_rail_stops_early_when_all_ais_out(tmp_path):
    cfg = config.Config(log_path=tmp_path / "log.jsonl")
    backends = {
        "claude": FakeBackend("claude", reply="hello from claude"),
        "codex": FakeBackend("codex", reply="hello from codex"),
    }
    # All are marked out or over pace
    statuses = {
        "claude": PlanStatus("claude", 20.0, 99.0, "out", []),
        "codex": PlanStatus("codex", 15.0, 90.0, "hard-only", []),
    }
    output = []
    code = room.run_room(
        room="testroom",
        max_turns=5,
        project="workshop",
        backends=backends,
        cfg=cfg,
        statuses=lambda: statuses,
        write=output.append,
    )
    assert code == 0
    assert any("all AIs are out of usage or over pace" in line for line in output)


def test_turn_cap_and_prompt_logging(tmp_path):
    cfg = config.Config(log_path=tmp_path / "log.jsonl", room_turn_cap=3)
    claude = FakeBackend("claude", reply="I'm on it! @codex what do you think?")
    codex = FakeBackend("codex", reply="Looks great. @claude we are rolling.")
    backends = {"claude": claude, "codex": codex}

    # Phil starts with a message
    room.say("hivelog", "Let's review the plan @claude", home=tmp_path)

    output = []
    code = room.run_room(
        room="hivelog",
        max_turns=3,
        project="workshop",
        backends=backends,
        cfg=cfg,
        statuses=lambda: {},
        write=output.append,
        home=tmp_path,
    )
    assert code == 0
    messages = room.read_messages("hivelog", home=tmp_path)
    # Phil's 1 message + 3 bot turns = 4 messages
    assert len(messages) == 4
    assert messages[1].author == "claude"
    assert messages[2].author == "codex"
    assert messages[3].author == "claude"

    # Verify prompt_chars is logged
    assert messages[1].prompt_chars > 0
    assert messages[2].prompt_chars > 0

    # Verify log.jsonl received room turns
    log_file = tmp_path / "log.jsonl"
    assert log_file.exists()
    logged_entries = [json.loads(l) for l in log_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert all(e["room"] == "hivelog" for e in logged_entries)
    assert sum(1 for e in logged_entries if e.get("lessons")) == 1  # the B2 end-of-session call
    logged_entries = [e for e in logged_entries if not e.get("lessons")]
    assert len(logged_entries) == 3
    assert all(e["prompt_chars"] > 0 for e in logged_entries)


def test_room_stop_command(tmp_path):
    room.set_stopped("stoproom", False, home=tmp_path)
    state = room.load_state("stoproom", home=tmp_path)
    assert not state.stopped

    room.stop("stoproom", home=tmp_path)
    state = room.load_state("stoproom", home=tmp_path)
    assert state.stopped


def test_room_pause_waits_for_current_fake_reply(tmp_path, monkeypatch):
    cfg = config.Config(log_path=tmp_path / "log.jsonl")
    room.say("pauseroom", "Please reply @codex", home=tmp_path)

    replies = 0
    def fake_reply(speaker, backend, prompt, resume):
        nonlocal replies
        replies += 1
        if replies == 1:
            room.set_paused("pauseroom", home=tmp_path)
        return "finished this reply", True, 0.1, ""

    monkeypatch.setattr(room, "run_speaker", fake_reply)
    output = []
    room.run_room("pauseroom", max_turns=4, project="sample",
                  backends={"codex": FakeBackend("codex")}, cfg=cfg,
                  statuses=lambda: {}, write=output.append, home=tmp_path)
    state = room.load_state("pauseroom", home=tmp_path)
    assert state.paused and not state.active
    assert [m.text for m in room.read_messages("pauseroom", home=tmp_path)] == [
        "Please reply @codex", "finished this reply"]
    assert any("paused after current reply" in line for line in output)

    room.run_room("pauseroom", max_turns=2, project="sample",
                  backends={"codex": FakeBackend("codex")}, cfg=cfg,
                  statuses=lambda: {}, write=output.append, home=tmp_path)
    state = room.load_state("pauseroom", home=tmp_path)
    assert state.turn_count == 2 and not state.paused and replies == 2


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

    # start for 2 turns
    code = main(["room", "start", "--turns", "2"], backends=backends, cfg=cfg)
    assert code == 0
    out = capsys.readouterr().out
    assert "[claude] Understood @codex" in out
    assert "[codex] Ready @claude" in out

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


def test_room_saves_lessons_and_next_card_shows_them(tmp_path):
    cfg = config.Config(log_path=tmp_path / "log.jsonl")
    claude = FakeBackend("claude", reply="- Check usage first\n- Mention one bot per reply")
    backends = {"claude": claude, "codex": FakeBackend("codex", reply="Ready @claude")}
    room.say("hive", "plan B2 @claude", home=tmp_path, write=lambda s: None)
    out = []
    room.run_room("hive", max_turns=3, project="workshop", backends=backends, cfg=cfg,
                  write=out.append, home=tmp_path)
    assert any("saved" in line and "lessons" in line for line in out)
    lessons = [e for e in Memory(tmp_path, "workshop").entries() if e.kind == "lesson"]
    assert lessons and lessons[-1].text == "Mention one bot per reply"
    card = room.build_state_card("workshop", tmp_path)
    assert "Lessons from earlier sessions:" in card and "Check usage first" in card


def test_short_room_session_skips_lessons(tmp_path):
    cfg = config.Config(log_path=tmp_path / "log.jsonl")
    claude = FakeBackend("claude", reply="- a lesson here")
    room.say("hive", "hi @claude", home=tmp_path, write=lambda s: None)
    room.run_room("hive", max_turns=2, project="workshop", backends={"claude": claude},
                  cfg=cfg, write=lambda s: None, home=tmp_path)
    assert len(claude.calls) == 2
    assert not [e for e in Memory(tmp_path, "workshop").entries() if e.kind == "lesson"]


def test_second_session_is_refused_while_first_is_alive(tmp_path):
    from datetime import datetime, timezone
    state = room.load_state("hive", tmp_path)
    state.active, state.session = True, "other"
    state.heartbeat = datetime.now(timezone.utc).isoformat(timespec="seconds")
    room.save_state(state, tmp_path)
    out = []
    code = room.run_room("hive", max_turns=1, project="workshop",
                         backends={"claude": FakeBackend("claude")},
                         cfg=config.Config(log_path=tmp_path / "log.jsonl"),
                         write=out.append, home=tmp_path)
    assert code == 1 and "already running" in out[-1]
    assert room.load_state("hive", tmp_path).session == "other"


def test_stale_session_does_not_block(tmp_path):
    state = room.load_state("hive", tmp_path)
    state.active, state.session, state.heartbeat = True, "dead", "2026-01-01T00:00:00+00:00"
    room.save_state(state, tmp_path)
    room.say("hive", "hi @claude", home=tmp_path, write=lambda s: None)
    code = room.run_room("hive", max_turns=1, project="workshop",
                         backends={"claude": FakeBackend("claude")},
                         cfg=config.Config(log_path=tmp_path / "log.jsonl"),
                         write=lambda s: None, home=tmp_path)
    assert code == 0 and not room.load_state("hive", tmp_path).active


def test_newer_session_takes_over_and_say_keeps_stop(tmp_path):
    room.set_stopped("hive", True, tmp_path)
    room.say("hive", "one more thing @claude", home=tmp_path, write=lambda s: None)
    assert room.load_state("hive", tmp_path).stopped  # typing after Stop doesn't un-stop

    class Takeover(FakeBackend):
        def _run(self, prompt):
            s = room.load_state("hive", tmp_path)
            s.session = "newer"
            room.save_state(s, tmp_path)
            return super()._run(prompt)

    bot = Takeover("claude", reply="hi")
    out = []
    room.run_room("hive", max_turns=5, project="workshop", backends={"claude": bot},
                  cfg=config.Config(log_path=tmp_path / "log.jsonl"), write=out.append,
                  home=tmp_path)
    assert len(bot.calls) == 1 and any("newer session" in line for line in out)
    assert room.load_state("hive", tmp_path).session == "newer"


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
