"""WIP cap tests: room text is authoritative; transport is always fake."""

import pytest

from megazword import config, room
from megazword.claims import active_claims, claim_conflicts
from megazword.cli import main


def message(text, id=1, author="claude-pc"):
    return dict(text=text, id=id, time="2026-10-19T12:00:00Z", author=author)


def test_claim_parsing_uses_text_prefix_and_preserves_metadata():
    rows = [message("Cedar-21: CLAIMING roadmap #10", 4),
            message("Birch-22: claiming item 11", 5),
            message("quoted Cedar-23: claiming #12"),
            message("claiming #13", author="Willow-24")]
    assert active_claims(rows) == {
        "Cedar-21": ("roadmap #10", 4, rows[0]["time"]),
        "Birch-22": ("item 11", 5, rows[1]["time"]),
    }


@pytest.mark.parametrize("release", ["releasing", "released", "landed #10", "item 10 done",
                                     "roadmap #10 done"])
def test_release_and_reclaim(release):
    rows = [message("Cedar-21: claiming roadmap #10"),
            message("cedar-21: " + release),
            message("Cedar-21: claiming item 11", 3)]
    assert active_claims(rows)["Cedar-21"][0:2] == ("item 11", 3)


def test_unrelated_done_and_other_seat_release_do_not_close_claim():
    rows = [message("Cedar-21: claiming #10"), message("Birch-22: released #10"),
            message("Cedar-21: done #100"), message("Cedar-21: claiming #11")]
    assert active_claims(rows)["Cedar-21"][0] == "#10"


def test_named_non_numbered_item_done():
    assert active_claims([message("Cedar-21: claiming fix tests"),
                          message("Cedar-21: fix tests landed")]) == {}


def test_conflicts_use_item_number_not_lane():
    claims = active_claims([message("Cedar-21: claiming roadmap #10"),
                            message("Birch-22: claiming item 10"),
                            message("Oak-23: claiming #100")])
    assert claim_conflicts(claims) == [("Cedar-21", "Birch-22", 10)]


@pytest.fixture
def local(tmp_path, monkeypatch):
    monkeypatch.delenv("HIVE_ROOM_URL", raising=False)
    monkeypatch.setattr(config, "HOME", tmp_path)
    return config.Config()


@pytest.mark.parametrize("text", ["cedar-21: claiming #11", "Birch-22: claiming item 10"])
def test_cli_refuses_cap_and_item_conflict(local, tmp_path, capsys, text):
    room.append_message("hive", "claude-pc", "Cedar-21: claiming #10", home=tmp_path)
    assert main(["room", "say", text], cfg=local, backends={}) == 1
    out = capsys.readouterr().out
    assert "post 'Cedar-21: releasing #10' first" in out
    assert len(out.splitlines()) == 1
    assert len(room.read_messages("hive", tmp_path)) == 1
    assert main(["room", "say", text, "--force"], cfg=local, backends={}) == 0
    assert len(room.read_messages("hive", tmp_path)) == 2


def test_cli_claims_prints_claims_and_conflicts(local, tmp_path, capsys):
    for text in ["Cedar-21: claiming #10", "Birch-22: claiming item 10"]:
        room.append_message("hive", "claude-pc", text, home=tmp_path)
    assert main(["room", "claims"], cfg=local, backends={}) == 0
    out = capsys.readouterr().out
    assert "Cedar-21: #10" in out and "Birch-22: item 10" in out
    assert "Conflict: Cedar-21 and Birch-22 both claim #10" in out


@pytest.mark.parametrize("offline", [False, True])
def test_remote_refresh_once_and_unreadable_room_posts(local, tmp_path, monkeypatch, offline):
    monkeypatch.setenv("HIVE_ROOM_URL", "https://room.example")
    calls = []

    class FakeRoom:
        def __init__(self, *args):
            pass

        def refresh(self):
            calls.append("refresh")
            if offline:
                raise OSError("offline")

        def cached(self):
            calls.append("cached")
            return [message("Cedar-21: claiming #10")]

        def flush(self, text):
            calls.append(text)
            return 0

    monkeypatch.setattr(room, "RemoteRoom", FakeRoom)
    text = "Cedar-21: claiming #11"
    assert room.say("hive", text, cfg=local, home=tmp_path, write=lambda _: None) == (0 if offline else 1)
    assert calls == (["refresh", text] if offline else ["refresh", "cached"])


def test_unreadable_local_room_posts(local, tmp_path, monkeypatch):
    monkeypatch.setattr(room, "read_messages", lambda *a: (_ for _ in ()).throw(OSError("unreadable")))
    assert room.say("hive", "Cedar-21: claiming #10", cfg=local, home=tmp_path) == 0
    assert "claiming #10" in room.room_path("hive", tmp_path).read_text()


def test_designation_with_lane_label_still_parses():
    claims = active_claims([message("Beacon-17 (claude-pc): claiming #9 spot warning")])
    assert claims["Beacon-17"][0] == "#9 spot warning"


def test_claims_older_than_a_day_expire():
    from datetime import datetime, timedelta, timezone
    rows = [message("Gauge-18: claiming #5 design")]
    noon = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)
    assert "Gauge-18" in active_claims(rows, now=noon + timedelta(hours=23))
    assert active_claims(rows, now=noon + timedelta(hours=25)) == {}
    assert "Gauge-18" in active_claims(rows)  # no clock: nothing expires
