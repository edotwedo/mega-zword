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
