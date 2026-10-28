"""Unit tests for megazword.sentry."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from megazword import room, sentry


def msg(author: str, text: str, remote_id: int = 1) -> room.RoomMessage:
    return room.RoomMessage(
        time="2026-10-27T12:00:00Z",
        author=author,
        text=text,
        remote_id=remote_id,
        remote_url="https://room.example",
    )


def test_get_seat_patterns():
    assert "mike" in sentry.get_seat_patterns("MIKE-54")
    assert "paul" in sentry.get_seat_patterns("Paul-53")
    assert "billy" in sentry.get_seat_patterns("Billy-55")
    assert "gavin" in sentry.get_seat_patterns("Gavin-27")
    assert "wenwei" in sentry.get_seat_patterns("WenWei-56")


def test_state_file_isolation(tmp_path):
    a = sentry.get_state_file("MIKE-54", "hive", home=tmp_path)
    b = sentry.get_state_file("Paul-53", "hive", home=tmp_path)
    assert a != b
    assert "MIKE_54" in a.name or "MIKE-54" in a.name
    assert "Paul_53" in b.name or "Paul-53" in b.name


def test_heuristic_ignores_own_messages():
    m = msg("MIKE-54", "MIKE-54: completed review")
    assert not sentry.check_actionable_heuristic(m, "MIKE-54")


def test_heuristic_ignores_closing_summary():
    m = msg("claude-pc", "CLOSING SUMMARY. All three items are done.")
    assert not sentry.check_actionable_heuristic(m, "MIKE-54")


def test_heuristic_detects_seat_directive():
    m = msg("Gavin-27", "MIKE-54: review task/578d7921105f on main.")
    assert sentry.check_actionable_heuristic(m, "MIKE-54")
    assert not sentry.check_actionable_heuristic(m, "Paul-53")


def test_heuristic_detects_phil_message():
    for author in ("phil", "phone", "grok-web"):
        m = msg(author, "look into the build failures pls")
        assert sentry.check_actionable_heuristic(m, "Billy-55")


def test_heuristic_detects_unassigned_work():
    m = msg("claude-pc", "FOUR ASSIGNMENTS. Unclaimed work is in play.")
    assert sentry.check_actionable_heuristic(m, "WenWei-56")


def test_heuristic_skips_assignments_to_other_seats():
    m = msg("Gavin-27", "ASSIGN -> Billy-55: wire Jev in as decision layer.")
    assert sentry.check_actionable_heuristic(m, "Billy-55")
    assert not sentry.check_actionable_heuristic(m, "Paul-53")


def test_check_actionable_jev(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "fake-key")

    mock_jd = MagicMock()
    mock_jd.choose.return_value = {"is_actionable": {"type": "noul", "noul": 0.85}}
    monkeypatch.setattr(sentry.decision, "JevDecision", lambda key: mock_jd)

    assert sentry.check_actionable_jev("review this PR", "MIKE-54")

    mock_jd.choose.return_value = {"is_actionable": {"type": "noul", "noul": 0.20}}
    assert not sentry.check_actionable_jev("lunch time", "MIKE-54")


def test_cli_room_sentry_parser():
    from megazword import cli
    parser = cli.build_parser()
    args = parser.parse_args(["room", "sentry", "--seat", "Billy-55", "--interval", "5", "--init-now"])
    assert args.command == "room"
    assert args.action == "sentry"
    assert args.seat == "Billy-55"
    assert args.interval == 5
    assert args.init_now is True
