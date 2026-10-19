"""Fake clocks, room messages and senders only: never send a real notification."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from megazword import config, escalate_watch as watch
from megazword.room import RoomMessage

START = datetime(2026, 10, 19, tzinfo=timezone.utc)
ROSTER = ["Beacon-17", "Juniper-16"]
SECRET = "private message text that must never leave the room"


def message(author="phil", text=SECRET, minute=0, remote_id=1):
    return RoomMessage((START + timedelta(minutes=minute)).isoformat(), author, text,
                       remote_id=remote_id)


class FakeRoom:
    def __init__(self, messages):
        self.messages = messages

    def refresh(self):
        pass

    def cached(self):
        return self.messages


def test_ladder_and_persistent_once_only_steps(tmp_path):
    room = FakeRoom([message()])
    state = tmp_path / "escalate.json"
    sends = []
    actions = []
    for minute in (4, 5, 5, 9, 10, 10, 14, 15, 15, 60):
        actions += watch.run_pass(room, START + timedelta(minutes=minute), ROSTER,
                                  state, "pc", "phone", lambda *args: sends.append(args))
    assert [(a.step, a.seat) for a in actions] == [(1, ROSTER[0]), (2, ROSTER[1]), (3, None)]
    assert sends == [("pc", "hive:1"), ("pc", "hive:1"), ("phone", watch.PHONE_BODY)]
    assert all(SECRET not in body for _, body in sends)
    assert json.loads(state.read_text()) == {"1": [1, 2, 3]}


def test_answer_at_seven_stops_after_first_step(tmp_path):
    room = FakeRoom([message()])
    sends = []
    state = tmp_path / "state.json"
    run = lambda minute: watch.run_pass(room, START + timedelta(minutes=minute), ROSTER,
                                        state, "pc", "phone", lambda *a: sends.append(a))
    assert len(run(5)) == 1
    room.messages.append(message("codex", "Beacon-17: on it", 7, 2))
    assert run(10) == run(15) == []
    assert sends == [("pc", "hive:1")]


@pytest.mark.parametrize("author", ["codex", "floor", "claude-web", "chatgpt", "grok-web"])
def test_bot_posts_are_never_calls(author):
    assert watch.escalate([message(author)], START + timedelta(minutes=20), ROSTER, {}) == []


@pytest.mark.parametrize("text", ["Reply to hive:1", "Taking #1", "answering call 1", "message #1 done"])
def test_explicit_call_references_answer(text):
    messages = [message(), message("bot", text, 7, 2)]
    assert watch.escalate(messages, START + timedelta(minutes=15), ROSTER, {}) == []


def test_only_later_answers_and_exact_call_ids_count():
    messages = [message("bot", "Beacon-17: earlier", -1, 0), message(),
                message("bot", "answering hive:10", 2, 2),
                message("phil", "Beacon-17: still waiting", 3, 3),
                message("bot", "Beacon-17: future", 20, 4)]
    actions = watch.escalate(messages, START + timedelta(minutes=5), ROSTER, {})
    assert [(a.call_id, a.step) for a in actions] == [(1, 1)]


def test_phone_lane_and_independent_calls():
    state = {}
    messages = [message(), message("phone", minute=4, remote_id=2)]
    assert [(a.call_id, a.step) for a in watch.escalate(
        messages, START + timedelta(minutes=10), ROSTER, state)] == [(1, 1), (1, 2), (2, 1)]
    assert watch.escalate(messages, START + timedelta(minutes=10), ROSTER, state) == []


def test_missing_roster_skips_directly_to_phone(tmp_path):
    assert watch.read_roster(tmp_path / "missing") == []
    assert watch.escalate([message()], START + timedelta(minutes=14), [], {}) == []
    actions = watch.escalate([message()], START + timedelta(minutes=15), [], {})
    assert [(a.step, a.body) for a in actions] == [(3, watch.PHONE_BODY)]


def test_roster_reads_seats_in_order_and_deduplicates(tmp_path):
    path = tmp_path / "roster.md"
    path.write_text("| Designation | Worker |\n| --- | --- |\n| Beacon-17 | bot |\n"
                    "| Juniper-16 | bot |\n| Beacon-17 | 1 |\n")
    assert watch.read_roster(path) == ROSTER


def test_no_topics_does_nothing(tmp_path):
    def fail(*args):
        pytest.fail("no topics must not send or refresh")
    room = FakeRoom([message()])
    room.refresh = fail
    path = tmp_path / "state.json"
    assert watch.run_pass(room, START + timedelta(minutes=20), ROSTER,
                          path, "", "", fail) == []
    assert not path.exists()


def test_failed_send_is_not_bookmarked(tmp_path):
    path = tmp_path / "state.json"
    def fail(*args):
        raise OSError("offline")
    with pytest.raises(OSError):
        watch.run_pass(FakeRoom([message()]), START + timedelta(minutes=5),
                       ROSTER, path, "pc", "phone", fail)
    assert not path.exists()


def test_phone_only_configuration_skips_seat_sends(tmp_path):
    sends = []
    path = tmp_path / "state.json"
    watch.run_pass(FakeRoom([message()]), START + timedelta(minutes=15), ROSTER,
                   path, "", "phone", lambda *a: sends.append(a))
    assert sends == [("phone", watch.PHONE_BODY)]
    assert json.loads(path.read_text()) == {"1": [3]}


def test_main_runs_one_pass_and_prints_actions(tmp_path, monkeypatch, capsys):
    room = FakeRoom([message()])
    room.url = "https://room.example"
    calls = []
    monkeypatch.setattr(watch, "RemoteRoom", lambda *a: room)
    monkeypatch.setattr(watch, "topics", lambda cfg: ("pc", "phone"))
    monkeypatch.setattr(watch, "read_roster", lambda: ROSTER)
    monkeypatch.setattr(watch, "run_pass", lambda *a: calls.append(a) or [
        watch.Action(1, 1, ROSTER[0], "hive:1")])
    monkeypatch.setattr(watch, "room_dir", lambda: tmp_path)
    assert watch.main([]) == 0
    assert len(calls) == 1
    assert calls[0][3].parent == tmp_path
    assert "step 1 sent to Beacon-17" in capsys.readouterr().out


def test_topics_from_config_and_existing_environment_conventions(tmp_path, monkeypatch):
    for name in ("MEGAZWORD_NTFY_PC_TOPIC", "MEGAZWORD_NTFY_PHONE_TOPIC",
                 "NTFY_PC_TOPIC", "NTFY_PHONE_TOPIC"):
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / "config.toml"
    path.write_text('[room]\nntfy_pc_topic = "pc"\nntfy_phone_topic = "phone"\n')
    cfg = config.load(path)
    assert watch.topics(cfg) == ("pc", "phone")
    monkeypatch.setenv("MEGAZWORD_NTFY_PC_TOPIC", "override")
    monkeypatch.setenv("NTFY_PHONE_TOPIC", "worker-phone")
    assert watch.topics(cfg) == ("override", "worker-phone")


def test_cli_dispatch(monkeypatch):
    from megazword import cli
    calls = []
    monkeypatch.setattr(watch, "main", lambda argv: calls.append(argv) or 0)
    assert cli.main(["room", "escalate", "--room", "test-room"]) == 0
    assert calls == [["--room", "test-room"]]
