"""Room API for the B4 Hive tab: say, disabled house bot, stop, view. Fakes only."""

from dataclasses import dataclass

import pytest

from megazword import cli, config, dashboard
from megazword.backends import Backend


@dataclass
class Fake(Backend):
    reply: str = "ok @codex"

    def _run(self, prompt):
        return self.reply


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(cli, "plan_statuses", lambda: {})
    cfg = config.Config(log_path=tmp_path / "log.jsonl")
    backends = {"claude": Fake("claude"), "codex": Fake("codex", reply="ready @claude")}
    return dashboard.App(cfg, "workshop", None, backends)


def test_invalid_send_options_do_not_post_an_unanswered_message(app):
    with pytest.raises(ValueError, match='turns'):
        app.room_say({'text': 'hello', 'start': True, 'turns': 500})
    assert app.room_view()['messages'] == []


def test_release_leaves_another_sessions_room_alone(tmp_path):
    room = dashboard.room
    state = room.load_state("hive", tmp_path)
    state.active, state.session = True, "someone-else"
    state.heartbeat = "2099-01-01T00:00:00+00:00"
    room.save_state(state, tmp_path)
    assert room.release("hive", "mine", tmp_path) is False
    assert room.load_state("hive", tmp_path).active
    assert room.release("hive", "someone-else", tmp_path) is True
    after = room.load_state("hive", tmp_path)
    assert after.paused and not after.active


def test_shutdown_without_a_room_does_nothing(app):
    app.shutdown()
    assert not dashboard.room.load_state("hive").active


def test_real_seats_only_even_with_legacy_start_request(app, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("house bot called")
    monkeypatch.setattr(dashboard.room, "run_room", forbidden)
    view = app.room_say({"text": "hello @claude", "start": True})
    assert [m["author"] for m in view["messages"]] == ["phil"]
    assert not view["running"] and app._room_thread is None
    with pytest.raises(ValueError, match="house bot disabled"):
        app.room_start({})
    app.room_stop({})
    assert dashboard.room.load_state("hive").stopped
