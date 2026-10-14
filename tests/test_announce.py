"""One-shot floor announce: Hive post, no @mentions, no model calls."""

from __future__ import annotations

import json
from types import SimpleNamespace

from megazword import announce, config, room


def test_clean_strips_mentions_and_secrets():
    text = announce.clean("  pause and read Q  @codex  @claude\n")
    assert "@" not in text
    assert "pause and read Q" == text


def test_post_writes_hive_and_announce_json(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(announce.config, "HOME", tmp_path)
    monkeypatch.setattr(room.config, "HOME", tmp_path)
    pings = []
    body = announce.post(
        "pause and read the Q update @grok",
        home=tmp_path,
        ping_fn=lambda msg, cfg: pings.append(msg),
    )
    assert body.startswith("ANNOUNCE:")
    assert "pause and read the Q update" in body
    assert "@grok" not in body
    assert "Stop new work" in body
    msgs = room.read_messages("hive", home=tmp_path)
    assert len(msgs) == 1
    assert msgs[0].author == "floor"
    assert msgs[0].text == body
    assert not msgs[0].mentions
    data = json.loads((tmp_path / "announce.json").read_text(encoding="utf-8"))
    assert data["text"] == "pause and read the Q update"
    assert data["body"] == body
    assert pings == [body]


def test_empty_announce_exits_2(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(announce.config, "HOME", tmp_path)
    out = []
    rc = announce.command(SimpleNamespace(text=["", "  "], room="hive"),
                          SimpleNamespace(ntfy_topic=""), write=out.append)
    assert rc == 2
    assert out[0].startswith("announce:")
    assert not (tmp_path / "announce.json").exists()


def test_floor_announce_uses_message(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from megazword import floor
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(announce.config, "HOME", tmp_path)
    monkeypatch.setattr(room.config, "HOME", tmp_path)
    monkeypatch.setattr(floor.config, "HOME", tmp_path)
    monkeypatch.setattr(floor, "save_snapshot", lambda seats: tmp_path / "floor.json")
    monkeypatch.setattr(announce, "ping", lambda *a, **k: None)
    out = []
    rc = floor.command(
        SimpleNamespace(action="announce", room="hive", message="pause and read Hive"),
        {}, SimpleNamespace(out_until={}, ntfy_topic=""), write=out.append,
    )
    assert rc == 0
    assert out[0].startswith("ANNOUNCE: pause and read Hive")
    assert room.read_messages("hive", home=tmp_path)[-1].author == "floor"


def test_command_prints_banner(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(announce.config, "HOME", tmp_path)
    monkeypatch.setattr(room.config, "HOME", tmp_path)
    monkeypatch.setattr(announce, "ping", lambda *a, **k: None)
    out = []
    rc = announce.command(
        SimpleNamespace(text=["pause", "and", "read", "Hive"], room="hive"),
        SimpleNamespace(ntfy_topic=""),
        write=out.append,
    )
    assert rc == 0
    assert out[0].startswith("ANNOUNCE: pause and read Hive")
    assert "hive_wait" in out[1]
