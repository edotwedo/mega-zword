"""Room API for the B4 Hive tab: say, start (background thread), stop, view. Fakes only."""

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


def test_say_start_and_view(app):
    view = app.room_say({"text": "plan the day @claude"})
    assert view["messages"][-1]["author"] == "phil" and not view["running"]
    app.room_start({"turns": 2})
    app._room_thread.join(10)
    view = app.room_view()
    authors = [m["author"] for m in view["messages"]]
    assert authors[:3] == ["phil", "claude", "codex"]
    assert view["turn_count"] == 2 and not view["running"]


def test_start_twice_is_refused_and_stop_sets_flag(app, monkeypatch):
    import threading
    gate = threading.Event()
    monkeypatch.setattr(dashboard.room, "run_room", lambda **kw: gate.wait(5))
    app.room_start({})
    with pytest.raises(ValueError, match="already running"):
        app.room_start({})
    app.room_stop({})
    assert dashboard.room.load_state("hive").stopped
    gate.set()
    app._room_thread.join(5)


def test_bad_input_is_rejected(app):
    with pytest.raises(ValueError):
        app.room_say({"text": "  "})
    with pytest.raises(ValueError):
        app.room_view("../etc")
    with pytest.raises(ValueError):
        app.room_start({"turns": 500})


def test_closing_the_dashboard_mid_session_pauses_the_room(app, tmp_path):
    """Closing the app window kills the room thread before its cleanup; the room must
    be resumable right away, not refused as 'running in another window' for 20 minutes."""
    import threading
    gate, started = threading.Event(), threading.Event()

    @dataclass
    class Slow(Fake):
        def _run(self, prompt):
            started.set()
            gate.wait(10)
            return self.reply

    app.backends["claude"] = Slow("claude")
    app.backends["codex"] = Slow("codex")
    app.room_say({"text": "go @claude"})
    app.room_start({"turns": 5})
    assert started.wait(5)
    app.shutdown()  # what serve() does when the window closes
    state = dashboard.room.load_state("hive")
    assert state.paused and not state.active
    assert not dashboard.room.other_session_running(state)
    gate.set()
    app._room_thread.join(10)


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
