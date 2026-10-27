"""Seat lifecycle: the roster, and the handoff when a seat runs out of context.

Phil, 2026-10-21: "if a user's context window get full, they are to retire and alert me
to the need for a replacement." Local files only, and the room post and the page are
injected, so these tests touch no network and no AI.
"""

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from megazword import seat
from megazword.room import RoomMessage

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
    expected = ("scripts/hive_resume.sh --only Harbor022"
                if seat.sys.platform.startswith("linux") else
                "pwsh -File scripts/hive_resume.ps1 -Only Harbor022")
    assert expected in text
    assert "You are Harbor022" in text
    assert "retired-harbor022.md" in text


def message(text, minutes_ago=0, id=1):
    return {"text": text, "time": (NOW - timedelta(minutes=minutes_ago)).isoformat(), "id": id}


def test_watch_reports_expired_but_unreleased_claims(monkeypatch, tmp_path):
    monkeypatch.setenv("MEGAZWORD_CLAIM_STALE_MINUTES", "45")
    calls = []

    def read(room, home):
        calls.append((room, home))
        return [message("Briar-20: claiming #8", 100)]

    rows = seat.watch(home=tmp_path, now=NOW, read=read)
    assert calls == [("hive", tmp_path)]
    assert rows == [{"designation": "Briar-20", "item": "#8", "claim_id": 1,
                     "last_seen": (NOW - timedelta(minutes=100)).isoformat(),
                     "silent_minutes": 100, "leash_minutes": 45}]


def test_watch_uses_latest_seat_update_not_claim_age_or_shared_lane(monkeypatch):
    monkeypatch.setenv("MEGAZWORD_CLAIM_STALE_MINUTES", "45")
    rows = [message("Briar-20: claiming #8", 150),
            message("Harbor022: claiming #9", 100),
            message("briar-20: tests are running", 5),
            message("Cinder-21: keeping the queue moving", 1)]
    for row in rows:
        row["author"] = "claude-pc"  # Shared transport does not prove a holder spoke.
    overdue = seat.watch(now=NOW, read=lambda *_: rows)
    assert [r["designation"] for r in overdue] == ["Harbor022"]
    assert overdue[0]["silent_minutes"] == 100


def test_watch_excludes_released_claims_and_non_claiming_seats(monkeypatch):
    monkeypatch.setenv("MEGAZWORD_CLAIM_STALE_MINUTES", "45")
    rows = [message("Briar-20: claiming #8", 100),
            message("Cinder-21: landed #8", 90),
            message("Harbor022: available for review", 100)]
    assert seat.watch(now=NOW, read=lambda *_: rows) == []


def test_watch_leash_boundary_and_future_messages(monkeypatch):
    monkeypatch.setenv("MEGAZWORD_CLAIM_STALE_MINUTES", "45")
    rows = [message("Briar-20: claiming #8", 45),
            message("Harbor022: claiming #9", 46),
            message("Forge-22: claiming #10", -5)]
    overdue = seat.watch(now=NOW, read=lambda *_: rows)
    assert [r["designation"] for r in overdue] == ["Harbor022"]


def test_watch_handles_dataclasses_naive_times_and_bad_timestamps(monkeypatch):
    monkeypatch.setenv("MEGAZWORD_CLAIM_STALE_MINUTES", "45")
    rows = [RoomMessage(time="2026-10-21T03:00:00", author="briar-20",
                        text="Briar-20: claiming 'seat watch'", remote_id=4),
            {"text": "Harbor022: claiming #9", "time": "unknown"},
            {"text": "Briar-20: still working", "time": "bad"}]
    overdue = seat.watch(now=NOW.replace(tzinfo=None), read=lambda *_: rows)
    assert len(overdue) == 1
    assert overdue[0]["designation"] == "Briar-20"
    assert overdue[0]["claim_id"] == 4
    assert overdue[0]["silent_minutes"] == 90


def test_watch_defaults_to_the_claims_leash_and_reads_floor_once(monkeypatch, tmp_path):
    from megazword import floor
    monkeypatch.delenv("MEGAZWORD_CLAIM_STALE_MINUTES", raising=False)
    calls = []

    def read(room, home):
        calls.append((room, home))
        return [message("Briar-20: claiming #8", 1441)]

    monkeypatch.setattr(floor, "room_messages", read)
    overdue = seat.watch("work", now=NOW, home=tmp_path)
    assert calls == [("work", tmp_path)]
    assert overdue[0]["leash_minutes"] == 1440


def test_watch_subcommand_prints_overdue_claim_without_retiring(monkeypatch):
    monkeypatch.setenv("MEGAZWORD_CLAIM_STALE_MINUTES", "45")
    from megazword import floor
    monkeypatch.setattr(floor, "room_messages", lambda *_: [
        message("Briar-20: claiming #8", 100)])
    real_watch = seat.watch
    monkeypatch.setattr(seat, "watch", lambda room: real_watch(room, now=NOW))
    parser = argparse.ArgumentParser()
    seat.add_parser(parser.add_subparsers(dest="command"))
    output = []
    assert seat.command(parser.parse_args(["seat", "watch", "--room", "work"]),
                        write=output.append) == 0
    assert len(output) == 1
    assert "Briar-20" in output[0] and "100m" in output[0] and "45m" in output[0]
    assert "#8" in output[0]


def test_watch_module_cli_reports_when_nobody_is_overdue(monkeypatch, capsys):
    from megazword import floor
    monkeypatch.setattr(floor, "room_messages", lambda *_: [])
    assert seat.main(["watch"]) == 0
    assert "no open claim holders" in capsys.readouterr().out


def test_a_seat_name_is_matched_whatever_case_the_caller_typed(tmp_path, monkeypatch):
    # Harbor022's review, 2026-10-21: `seat retire harbor022` matched nothing, so the handoff
    # said "unknown CLI" and replace printed no CLI at all. The roster row says Harbor022.
    monkeypatch.setattr(seat, "roster", roster_rows)
    assert seat.cli_for("harbor022") == "claude"
    assert seat.cli_for("Harbor022") == "claude"
    assert seat.cli_for("nobody-99") == ""

    monkeypatch.setattr(seat, "HANDOFFS", tmp_path / "handoffs")
    result = seat.retire("harbor022", next_step="x", home=tmp_path, now=NOW,
                         say=lambda *args: None, ping=lambda body: None)
    written = Path(result["handoff"]).read_text(encoding="utf-8")
    assert "(claude)" in written, "the handoff must name the CLI even when the case differs"


def test_status_shows_what_a_seat_last_said_when_it_has_no_card(tmp_path, monkeypatch):
    # No seat publishes a briefing card yet, so a card-only status called every seat "no card"
    # while three of them had been posting all night. The room already knows better.
    monkeypatch.setattr(seat, "roster", roster_rows)
    monkeypatch.setattr(seat, "directory", lambda name: tmp_path / name.lower())
    monkeypatch.setattr(seat, "room_summary", lambda home=None: {
        "harbor022": {"designation": "Harbor022", "counts": {"status": 1},
                      "last_kind": "status", "last": "reviewing the mirror"},
    })
    rows = {row["designation"]: row for row in seat.status_rows(tmp_path)}
    assert rows["Harbor022"]["state"] == "status"
    assert rows["Harbor022"]["from_room"] is True
    assert "reviewing the mirror" in seat.render_status(seat.status_rows(tmp_path))
    # A seat that has said nothing at all still reads honestly.
    assert rows["Cinder-21"]["state"] == ""


def test_replace_keeps_windows_command(monkeypatch):
    monkeypatch.setattr(seat.sys, "platform", "win32")
    monkeypatch.setattr(seat, "status_rows", lambda: [])
    monkeypatch.setattr(seat, "newest_handoff", lambda _: None)
    assert "pwsh -File scripts/hive_resume.ps1 -Only Gavin-27" in seat.replace_text("Gavin-27")
