"""The hive relevance filter: a seat polls often, but answers only its own business.

Phil, 2026-10-25: a seat should check the room "often enough that it is indistinguishable
from a team of coders keeping each others work going". Polling that often is only safe if the
filter is honest about what is not for this seat, so these cover the decision, the quiet
count that proves the seat is still listening, and the monotonic tick that keeps `--health`
from answering "Ready". Offline: fake message dicts and an injected reader, no network.
"""

import argparse
import json
from datetime import datetime, timedelta, timezone

from megazword import wake


def message(text, author="briar-20", id=1):
    return {"id": id, "author": author, "text": text}


def test_a_phil_author_wakes():
    assert wake.relevance(message("who is on #12", "phil"), "Cinder-21") == "phil"
    assert wake.relevance(message("", "phone"), "Cinder-21") == "phil"
    assert wake.relevance(message("", "grok-web"), "Cinder-21") == "phil"


def test_a_plain_mention_wakes_however_it_is_spelled():
    for text in ("Cinder-21, can you take the lock?", "hey cinder 21 look here", "cinder21 status?"):
        assert wake.relevance(message(text), "Cinder-21") == "mention"
    assert wake.relevance(message("CINDER-21 ping"), "Cinder-21") == "mention"


def test_an_assignment_addressed_to_the_seat_wakes(monkeypatch):
    assert wake.relevance(message("Cinder-21: do the F1d tick"), "Cinder-21") is not None
    # is_wake asks the same question, with this seat taken from the environment.
    monkeypatch.setenv("MEGAZWORD_SEAT", "Cinder-21")
    assert wake.is_wake("Cinder-21: do the F1d tick", "harbor022") is True
    monkeypatch.setenv("MEGAZWORD_SEAT", "Nock-21")
    assert wake.is_wake("Cinder-21: do the F1d tick", "harbor022") is False


def test_a_landing_on_my_claimed_item_wakes():
    landing = message("Harbor022: landed #5, it is in main", author="harbor022", id=9)
    assert wake.relevance(landing, "Cinder-21", claims=("#5",)) == "my-item"
    # Someone else's item is not mine, even when it lands.
    assert wake.relevance(message("Harbor022: landed #9"), "Cinder-21", claims=("#5",)) is None
    # A quoted claim works the same way.
    assert wake.relevance(message("claim lock released"), "Cinder-21",
                          claims=("'claim lock'",)) == "my-item"


def test_a_broadcast_roll_call_wakes():
    for text in ("Broadcast: everyone stand down", "every seat report status",
                 "all seats, read the draft", "roll call"):
        assert wake.relevance(message(text), "Cinder-21") == "broadcast"


def test_another_seats_chatter_does_not_wake(tmp_path):
    rows = [message("Briar-20: landed #9 and took #11", author="briar-20", id=4),
            message("Nock-21: blocked on the worker", author="nock-21", id=5)]
    for row in rows:
        assert wake.relevance(row, "Cinder-21") is None
    output = []
    assert wake.once(home=tmp_path, read=lambda: rows, write=output.append, me="Cinder-21") == 0
    assert output == [], "another seat's work must not type into this seat's tab"


def test_the_digest_fires_once_then_goes_quiet():
    now = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
    state = {"suppressed": 4}
    assert wake.digest(state, now) == "hive: 4 messages, none for you"
    assert state["suppressed"] == 0 and state["digest_at"] == "2026-10-25T12:00:00+00:00"
    # Inside the hour there is nothing new to say, even with a fresh count.
    state["suppressed"] = 3
    assert wake.digest(state, now + timedelta(minutes=59)) is None
    # Past the hour the new count is reported.
    assert wake.digest(state, now + timedelta(minutes=61)) == "hive: 3 messages, none for you"


def test_the_digest_says_nothing_when_the_seat_heard_nothing():
    now = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
    assert wake.digest({"suppressed": 0}, now) is None
    # Even an overdue digest has nothing to report with a zero count.
    assert wake.digest({"suppressed": 0, "digest_at": (now - timedelta(hours=2)).isoformat()}, now) is None


def test_tick_age_reports_stale_past_the_health_threshold(tmp_path):
    now = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
    state = tmp_path / "wake.json"
    state.write_text(json.dumps({"tick": 42, "at": (now - timedelta(seconds=60)).isoformat(timespec="seconds")}),
                     encoding="utf-8")
    assert wake.tick_age(tmp_path, now=now) == 60
    assert wake.health(tmp_path, now=now, write=lambda *_: None) == 0

    state.write_text(json.dumps({"tick": 42, "at": (now - timedelta(seconds=200)).isoformat(timespec="seconds")}),
                     encoding="utf-8")
    age = wake.tick_age(tmp_path, now=now)
    assert age is not None and age > 180, "3 missed 60s polls means the listener is down"
    printed = []
    assert wake.health(tmp_path, now=now, write=printed.append) == 1
    assert printed == ["tick 42, age 200s"]

    # Never having polled is not healthy either.
    state.unlink()
    assert wake.tick_age(tmp_path, now=now) is None
    assert wake.health(tmp_path, now=now, write=lambda *_: None) == 1


def test_a_poll_records_the_tick_and_counts_what_it_let_pass(tmp_path, capsys):
    rows = [message("Briar-20: landed #9", author="briar-20", id=7)]
    assert wake.once(home=tmp_path, read=lambda: rows, write=lambda *_: None, me="Cinder-21") == 0
    state = json.loads((tmp_path / "wake.json").read_text(encoding="utf-8"))
    assert state["tick"] == 7 and state["suppressed"] == 1 and wake.last_seen(tmp_path) == 7
    # The same backlog is not counted twice.
    wake.once(home=tmp_path, read=lambda: rows, write=lambda *_: None, me="Cinder-21")
    assert json.loads((tmp_path / "wake.json").read_text(encoding="utf-8"))["suppressed"] == 1
    # `megazword wake --digest` prints the quiet hour, and only once.
    args = argparse.Namespace(home=tmp_path, digest=True, health=False, ack=None, peek=False, json=False)
    assert wake.command(args) == 0
    assert capsys.readouterr().out.strip() == "hive: 1 messages, none for you"
    assert wake.command(args) == 0
    assert capsys.readouterr().out == ""
