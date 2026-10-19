"""Fakes only: no network, no real room, no real ntfy."""

from __future__ import annotations

import json

from megazword import room, room_wait


def msg(author, remote_id):
    return room.RoomMessage(time="2026-10-19T00:00", author=author, text=author + " says hi",
                            remote_id=remote_id, remote_url="https://room.example")


class FakeRoom:
    """cached() serves the batch for the current refresh count, so refresh() moves time on."""

    def __init__(self, *batches):
        self.batches = list(batches)
        self.calls = 0

    def refresh(self):
        self.calls += 1

    def cached(self):
        return list(self.batches[min(self.calls - 1, len(self.batches) - 1)])


class FakeStream:
    def __init__(self, lines):
        self.lines = lines

    def __enter__(self):
        return iter(self.lines)

    def __exit__(self, *exc):
        return False


def line(event, message=""):
    return json.dumps({"event": event, "message": message}).encode("utf-8")


def test_returns_early_on_unseen_phil_message(tmp_path):
    state = tmp_path / "state.json"
    state.write_text('{"last": 3}', encoding="utf-8")
    room_obj = FakeRoom([msg("codex", 2), msg("phil", 4), msg("codex", 5)])

    def opener(*args, **kwargs):
        raise AssertionError("must not open a stream when the cache already answers")

    got = room_wait.wait_for_phil(room_obj, "t", state, opener=opener, sleep=lambda s: None)
    assert [m.remote_id for m in got] == [4]
    assert json.loads(state.read_text(encoding="utf-8"))["last"] == 4


def test_ignores_bots_and_non_hive_lines(tmp_path):
    state = tmp_path / "s.json"
    lines = [line("open"), line("message", "other:9"), line("message", "codex said hi"),
             line("message", "hive:9")]
    room_obj = FakeRoom([msg("codex", 5)], [msg("codex", 5), msg("grok", 6), msg("phil", 7)])
    got = room_wait.wait_for_phil(room_obj, "t", state,
                                  opener=lambda url, timeout=None: FakeStream(lines),
                                  sleep=lambda s: None)
    assert [m.author for m in got] == ["phil"] and got[0].remote_id == 7
    assert room_obj.calls == 2  # start refresh + the one real signal, nothing else
    assert json.loads(state.read_text(encoding="utf-8"))["last"] == 7


def test_state_file_written_when_missing(tmp_path):
    state = tmp_path / "nested" / "s.json"
    room_obj = FakeRoom([msg("claude-web", 1)])
    got = room_wait.wait_for_phil(room_obj, "t", state, sleep=lambda s: None)
    assert [m.remote_id for m in got] == [1]
    assert json.loads(state.read_text(encoding="utf-8"))["last"] == 1


def test_backoff_doubles_then_caps(tmp_path):
    sleeps = []
    room_obj = FakeRoom([], [msg("phil", 1)])
    attempts = {"n": 0}

    def opener(url, timeout=None):
        attempts["n"] += 1
        if attempts["n"] < 9:
            raise OSError("room down")
        return FakeStream([line("message", "hive:1")])

    got = room_wait.wait_for_phil(room_obj, "t", tmp_path / "s.json",
                                  opener=opener, sleep=sleeps.append)
    assert [m.remote_id for m in got] == [1]
    assert sleeps == [5, 10, 20, 40, 80, 160, 300, 300]


def test_main_prints_each_message(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(room_wait, "RemoteRoom", lambda *a, **k: object())
    monkeypatch.setattr(room_wait.config, "load", lambda: object())
    monkeypatch.setattr(room_wait, "wait_for_phil",
                        lambda *a, **k: [msg("phil", 1), msg("chatgpt", 2)])
    assert room_wait.main(["--room", "hive", "--state", str(tmp_path / "s.json")]) == 0
    out = capsys.readouterr().out
    assert "2026-10-19T00:00 [phil] phil says hi" in out
    assert "[chatgpt]" in out
