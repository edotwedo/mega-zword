"""Command Code's own meter, totalled from its local session transcripts.

These tests pin the two things that would make the number a lie: counting a call
outside the window, and inventing a percentage we cannot know.
"""

import json
from datetime import datetime, timedelta, timezone

from megazword import usage_sources

NOW = datetime(2026, 10, 19, 8, 0, tzinfo=timezone.utc)


def transcript(root, slug, session, lines):
    folder = root / slug
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{session}.jsonl"
    path.write_text("".join(lines), encoding="utf-8")
    return path


def turn(when, cost, tin=1000, tout=100):
    """One committed turn, the shape the CLI writes."""
    entry = {
        "type": "message",
        "timestamp": when.isoformat().replace("+00:00", "Z"),
        "model": "deepseek/deepseek-v4-flash",
        "usage": {"inputTokens": tin, "outputTokens": tout,
                  "cacheReadTokens": 0, "cacheWriteTokens": 0, "costUsd": cost},
    }
    return json.dumps(entry) + "\n"


def test_totals_the_recent_window_and_the_week(tmp_path):
    transcript(tmp_path, "c-users-mrmar-mega-zword", "a", [
        turn(NOW - timedelta(hours=1), 0.25),
        turn(NOW - timedelta(days=3), 1.50),
    ])
    plan = usage_sources.command_code(tmp_path, NOW)
    assert plan.service == "cmdc"
    assert plan.windows == []          # no plan meter, so no bar
    assert "$0.25/5h" in plan.note
    assert "$1.75/7d" in plan.note


def test_a_call_older_than_the_week_is_not_counted(tmp_path):
    transcript(tmp_path, "slug", "a", [turn(NOW - timedelta(days=9), 9.99)])
    plan = usage_sources.command_code(tmp_path, NOW)
    assert plan.windows == []
    assert plan.note == "no Command Code usage in the last 7 days"


def test_header_and_unreadable_lines_are_skipped(tmp_path):
    path = transcript(tmp_path, "slug", "a", [turn(NOW, 0.10)])
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"type": "session", "id": "abc"}\n')          # no usage key
        fh.write('{"usage": not json\n')                        # broke mid-write
        fh.write('{"type": "message", "timestamp": "garbage", '  # unusable stamp
                 '"usage": {"costUsd": 5.0}}\n')
    plan = usage_sources.command_code(tmp_path, NOW)
    assert "$0.10/7d" in plan.note


def test_an_empty_home_reports_nothing_rather_than_zero(tmp_path):
    plan = usage_sources.command_code(tmp_path, NOW)
    assert plan.note == "no Command Code usage in the last 7 days"


def test_reads_the_real_home_when_no_folder_is_given(tmp_path, monkeypatch):
    monkeypatch.setattr(usage_sources, "COMMAND_CODE_ROOT", tmp_path)
    transcript(tmp_path, "slug", "a", [turn(NOW - timedelta(minutes=5), 0.05)])
    assert "$0.05/5h" in usage_sources.command_code(now=NOW).note


def test_registered_so_every_usage_view_picks_it_up():
    assert usage_sources.SOURCES["cmdc"] is usage_sources.command_code


def test_a_weeks_tokens_read_as_millions_not_hundreds_of_thousands(tmp_path):
    # A real week is ~200M tokens; 196869k tok on screen is unreadable.
    transcript(tmp_path, "slug", "a", [turn(NOW, 0.01, tin=3_400_000, tout=0)])
    assert "3M tok" in usage_sources.command_code(tmp_path, NOW).note
