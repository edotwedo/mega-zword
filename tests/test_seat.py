"""Seat lifecycle: the roster, and the handoff when a seat runs out of context.

Phil, 2026-10-21: "if a user's context window get full, they are to retire and alert me
to the need for a replacement." Local files only, and the room post and the page are
injected, so these tests touch no network and no AI.
"""

from datetime import datetime, timezone
from pathlib import Path

from megazword import seat

NOW = datetime(2026, 10, 21, 4, 30, tzinfo=timezone.utc)


def roster_rows():
    return [("Cinder-21", "cmdc"), ("Harbor022", "claude")]


def test_status_lists_the_roster_and_says_when_a_worktree_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(seat, "roster", roster_rows)
    monkeypatch.setattr(seat, "directory", lambda name: tmp_path / name.lower())
    rendered = seat.render_status(seat.status_rows(tmp_path))
    assert "Cinder-21" in rendered and "Harbor022" in rendered
    assert "NO WORKTREE" in rendered
    assert "never" in rendered  # nothing published a card yet


def test_a_card_published_by_the_seat_shows_up_in_status(tmp_path, monkeypatch):
    monkeypatch.setattr(seat, "roster", roster_rows)
    monkeypatch.setattr(seat, "directory", lambda name: tmp_path / name.lower())
    seat.publish({"seat": "Harbor022", "state": "working", "next": "review the Worker"},
                 home=tmp_path)
    rows = {row["designation"]: row for row in seat.status_rows(tmp_path)}
    assert rows["Harbor022"]["state"] == "working"
    assert rows["Harbor022"]["next"] == "review the Worker"


def test_retire_writes_the_handoff_posts_one_line_and_pages_phil(tmp_path, monkeypatch):
    monkeypatch.setattr(seat, "roster", roster_rows)
    monkeypatch.setattr(seat, "HANDOFFS", tmp_path / "handoffs")
    posted, paged = [], []
    result = seat.retire(
        "Harbor022", next_step="finish #21 then stop", reason="context full",
        home=tmp_path, now=NOW,
        say=lambda room, text, author: posted.append((room, text, author)),
        ping=lambda body: paged.append(body),
    )
    handoff = Path(result["handoff"])
    assert handoff.exists()
    assert "finish #21 then stop" in handoff.read_text(encoding="utf-8")

    assert posted and posted[0][2] == "Harbor022"
    assert "retire" in posted[0][1] and "context full" in posted[0][1]
    assert paged and "replacement is needed" in paged[0]

    card = seat.cards(tmp_path)["harbor022"]
    assert card["state"] == "done"
    assert card["next"] == "finish #21 then stop"


def test_a_dead_room_does_not_lose_the_handoff(tmp_path, monkeypatch):
    monkeypatch.setattr(seat, "roster", roster_rows)
    monkeypatch.setattr(seat, "HANDOFFS", tmp_path / "handoffs")

    def dead_room(*_args, **_kwargs):
        raise OSError("room down")

    result = seat.retire("Harbor022", next_step="x", home=tmp_path, now=NOW,
                         say=dead_room, ping=lambda body: None)
    assert Path(result["handoff"]).exists()
    assert "room post failed" in result["room_note"]


def test_replace_prints_the_relaunch_line_and_the_first_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr(seat, "roster", roster_rows)
    monkeypatch.setattr(seat, "HANDOFFS", tmp_path / "handoffs")
    monkeypatch.setattr(seat, "SEATS_ROOT", tmp_path / "mz-seats")
    monkeypatch.setattr(seat, "directory", lambda name: tmp_path / "mz-seats" / name.lower())
    seat.retire("Harbor022", next_step="finish #21", home=tmp_path, now=NOW,
                say=lambda *args: None, ping=lambda body: None)
    text = seat.replace_text("Harbor022")
    assert "hive_resume.ps1 -Only Harbor022" in text
    assert "You are Harbor022" in text
    assert "retired-harbor022.md" in text
