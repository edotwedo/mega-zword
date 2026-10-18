"""Cloud room behavior without a real token, network or Cloudflare account."""
import io
import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from megazword import config, keys, room
from megazword.cli import main


@pytest.fixture
def remote(tmp_path, monkeypatch):
    monkeypatch.setenv("HIVE_ROOM_URL", "https://room.example")
    monkeypatch.delenv("HIVE_ROOM_TOKEN", raising=False)
    monkeypatch.setattr(keys.vault, "read", lambda name: str(uuid.uuid4()) if name == "HIVE_ROOM_TOKEN" else None)
    # Stable in-memory fake credential for queue replay.
    fake = str(uuid.uuid4())
    monkeypatch.setattr(keys, "get_key", lambda name: fake)
    rows, attempts = [], []
    state = {"offline": False, "lose_response": False}

    def request(self, method, suffix="", item=None):
        attempts.append((method, suffix, item))
        if state["offline"]:
            raise OSError("offline")
        if method == "POST":
            found = next((r for r in rows if r["key"] == item["id"]), None)
            if not found:
                found = dict(id=len(rows)+1, text=item["text"], author="cirrus-17", time="2026-10-17T00:00:00Z", key=item["id"])
                rows.append(found)
            if state["lose_response"]:
                state["lose_response"] = False
                raise OSError("response lost after commit")
            return {"message": found}
        since = int(suffix.split("since=")[1].split("&")[0])
        return {"messages": [r for r in rows if r["id"] > since][:200]}

    monkeypatch.setattr(room.RemoteRoom, "request", request)
    return config.Config(room_url="https://room.example"), rows, attempts, state


def test_queue_survives_outage_and_replays_next_show(remote, tmp_path):
    cfg, rows, calls, state = remote
    state["offline"] = True
    out = []
    room.say("hive", "hello 😀", author="someone-else", cfg=cfg, home=tmp_path, write=out.append)
    assert "1 queued" in out[-1]
    queue = next(room.room_dir(tmp_path).glob("*.queue.json"))
    assert json.loads(queue.read_text())[0]["text"] == "hello 😀"
    state["offline"] = False
    room.show("hive", cfg=cfg, home=tmp_path, write=out.append)
    assert json.loads(queue.read_text()) == []
    assert len(rows) == 1 and "[cirrus-17]" in out[-1]


def test_lost_response_deduplicates_after_retry(remote, tmp_path):
    cfg, rows, calls, state = remote
    state["lose_response"] = True
    room.say("hive", "once", cfg=cfg, home=tmp_path, write=lambda _: None)
    room.show("hive", cfg=cfg, home=tmp_path, write=lambda _: None)
    assert len(rows) == len(room.read_messages("hive", tmp_path)) == 1
    posts = [c[2]["id"] for c in calls if c[0] == "POST"]
    assert len(posts) == 2 and posts[0] == posts[1]


def test_offline_show_labels_cache_and_pending(remote, tmp_path):
    cfg, rows, calls, state = remote
    room.say("hive", "cached", cfg=cfg, home=tmp_path, write=lambda _: None)
    state["offline"] = True
    room.say("hive", "pending", cfg=cfg, home=tmp_path, write=lambda _: None)
    out = []
    room.show("hive", cfg=cfg, home=tmp_path, write=out.append)
    assert any("local cache" in line for line in out)
    assert any("1 messages still queued" in line for line in out)
    assert "cached" in out[-1]


def test_post_does_not_skip_intervening_history_and_pages(remote, tmp_path):
    cfg, rows, calls, state = remote
    for i in range(401):
        rows.append(dict(id=i+1, text=str(i), author="beacon-17", time="2026-10-17T00:00:00Z", key=str(i)))
    room.say("hive", "last", cfg=cfg, home=tmp_path, write=lambda _: None)
    room.show("hive", n=500, cfg=cfg, home=tmp_path, write=lambda _: None)
    assert [m.remote_id for m in room.read_messages("hive", tmp_path)] == list(range(1, 403))
    assert len([c for c in calls if c[0] == "GET"]) == 3


def test_queues_are_bound_to_origin_and_credential(remote, tmp_path, monkeypatch):
    cfg, rows, calls, state = remote
    state["offline"] = True
    room.say("hive", "private pending", cfg=cfg, home=tmp_path, write=lambda _: None)
    monkeypatch.setattr(keys, "get_key", lambda name: str(uuid.uuid4()))
    state["offline"] = False
    room.show("hive", cfg=cfg, home=tmp_path, write=lambda _: None)
    assert rows == []


def test_missing_key_is_explicit_and_never_posts_local(remote, tmp_path, monkeypatch):
    cfg, *_ = remote
    monkeypatch.setattr(keys, "get_key", lambda name: None)
    with pytest.raises(ValueError, match="HIVE_ROOM_TOKEN missing"):
        room.say("hive", "hi", cfg=cfg, home=tmp_path)
    assert not room.room_path("hive", tmp_path).exists()


@pytest.mark.parametrize("url", ["http://room.example", "https://user:password@room.example", "https://room.example/path", "https://room.example?token=anything"])
def test_rejects_unsafe_origins(remote, tmp_path, monkeypatch, url):
    monkeypatch.setenv("HIVE_ROOM_URL", url)
    with pytest.raises(ValueError, match="HTTPS origin"):
        room.RemoteRoom("hive", remote[0], tmp_path)


def test_transport_uses_keymaster_header_timeout_and_retry_key(tmp_path, monkeypatch):
    fake = str(uuid.uuid4())
    monkeypatch.delenv("HIVE_ROOM_URL", raising=False)
    monkeypatch.delenv("HIVE_ROOM_TOKEN", raising=False)
    monkeypatch.setattr(keys.vault, "read", lambda name: fake if name == "HIVE_ROOM_TOKEN" else None)
    seen = {}
    class Opener:
        def open(self, req, timeout):
            seen.update(headers=dict(req.header_items()), timeout=timeout, body=json.loads(req.data))
            return io.StringIO('{"message": {}}')
    monkeypatch.setattr(room.urllib.request, "build_opener", lambda *handlers: Opener())
    client = room.RemoteRoom("hive", config.Config(room_url="https://room.example"), tmp_path)
    client.request("POST", item={"id": "retry-id", "text": "hi"})
    assert seen["headers"]["Authorization"] == "Bearer " + fake
    assert seen["headers"]["Idempotency-key"] == "retry-id"
    assert not seen["headers"]["User-agent"].startswith("Python-urllib")  # Cloudflare 1010
    assert seen["timeout"] == 10 and seen["body"] == {"text": "hi"}
    assert not list(tmp_path.rglob("*.json"))


def test_local_emoji_on_cp1252_console(tmp_path, monkeypatch):
    sink = io.BytesIO()
    stream = io.TextIOWrapper(sink, encoding="cp1252")
    monkeypatch.setattr(room.sys, "stdout", stream)
    writer = lambda text: print(text, file=stream)
    room.say("hive", "hello 😀", cfg=config.Config(), home=tmp_path, write=writer)
    room.show("hive", cfg=config.Config(), home=tmp_path, write=writer)
    stream.flush()
    assert b"hello ?" in sink.getvalue()


def test_house_bot_never_runs_and_never_posts_summary(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("room invoked an AI or posted a summary")
    monkeypatch.setattr(room, "default_backends", forbidden)
    monkeypatch.setattr(room, "post_summary", forbidden)
    monkeypatch.setattr(room, "run_speaker", forbidden)
    assert room.run_room(home=tmp_path, write=lambda _: None) == 0
    assert not room.room_path("hive", tmp_path).exists()


def test_cli_passes_config_to_remote(remote, tmp_path, monkeypatch, capsys):
    cfg, rows, *_ = remote
    monkeypatch.setattr(config, "HOME", tmp_path)
    assert main(["room", "say", "cli"], cfg=cfg, backends={}) == 0
    assert main(["room", "show"], cfg=cfg, backends={}) == 0
    assert "[cirrus-17]" in capsys.readouterr().out


def test_config_and_keymaster_registration(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text('[room]\nurl = "https://room.example"\n')
    assert config.load(path).room_url == "https://room.example"
    assert "HIVE_ROOM_TOKEN" in keys.key_names()


def test_d1_schema_atomic_rate_sql_and_indexes():
    base = Path(__file__).resolve().parents[1] / "cloud" / "hive-room"
    db = sqlite3.connect(":memory:")
    db.executescript((base / "schema.sql").read_text())
    source = (base / "index.js").read_text()
    sql = source.split('prepare(`INSERT', 1)[1].split('`)', 1)[0]
    sql = 'INSERT' + sql
    args = lambda key: ("hive", "cirrus-17", "hi", "2026-10-17T00:00:30.000Z", key, "cirrus-17", "2026-10-16T23:59:30.000Z")
    for i in range(30):
        assert db.execute(sql, args(str(i))).fetchone() is not None
    assert db.execute(sql, args("overflow")).fetchone() is None
    assert db.execute(sql, args("0")).fetchone() is None
    assert db.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 30
    plan = str(db.execute('EXPLAIN QUERY PLAN SELECT * FROM messages WHERE room=? AND id>? ORDER BY id LIMIT ?', ('hive', 0, 100)).fetchall())
    assert "room_cursor" in plan
