"""Phil is identified by exclusion against the seat roster, not a lane list."""

import pytest

from megazword import room, room_wait, wake


@pytest.mark.parametrize("author", ["claude-cloud", "claude-web", "phone", "grok-web", "phil"])
def test_non_roster_lanes_are_phil_everywhere(author):
    assert room.is_phil(author)
    assert wake.is_wake("", author)
    assert room_wait._unseen(type("R", (), {"cached": lambda self: [
        room.RoomMessage("", author, "hello", remote_id=1)
    ]})(), 0)


def test_rostered_designation_is_a_seat_not_phil():
    assert not room.is_phil("MIKE-54")
    assert not wake.is_wake("", "MIKE-54")


def test_roster_changes_are_read_without_a_lane_config(tmp_path, monkeypatch):
    roster = tmp_path / "HIVE-ROSTER.md"
    roster.write_text("| Active seat | Worker |\n| --- | --- |\n| NewSeat | Codex |\n")
    monkeypatch.setattr(room, "HIVE_ROSTER", roster)
    assert not room.is_phil("newseat")
    assert room.is_phil("new-lane")
