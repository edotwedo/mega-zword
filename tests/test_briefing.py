"""Reports stay factual, bounded, local, and readable without model calls."""

import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from megazword import briefing, cli, config, mcp_hive

NOW = datetime(2026, 10, 14, 20, tzinfo=timezone.utc)


def test_reports_round_trip_and_one_seat_replaces_its_own_card(tmp_path):
    briefing.publish({"seat": "Cedar-14", "doing": "testing", "next": "push"}, tmp_path, NOW)
    briefing.publish({"seat": "Testlog-14", "project": "mega-zword", "state": "done",
                      "done": "16 tests", "blocked": "review", "next": "combine"}, tmp_path, NOW)
    briefing.publish({"seat": "Cedar-14", "doing": "reviewing"}, tmp_path, NOW)
    data = briefing.snapshot(tmp_path, NOW)
    assert [c["seat"] for c in data["cards"]] == ["cedar-14", "testlog-14"]
    cedar, testlog = data["cards"]
    assert cedar["doing"] == "reviewing" and cedar["next"] == ""
    assert testlog["done"] == "16 tests" and testlog["state"] == "done"
    text = briefing.render(data)
    assert "Blocked by: review" in text and "Next: combine" in text
    assert "Just done: not reported" in text


def test_stale_snapshots_are_labeled_and_sorted_after_recent(tmp_path):
    briefing.publish({"seat": "old"}, tmp_path, NOW - timedelta(hours=1))
    briefing.publish({"seat": "recent"}, tmp_path, NOW)
    data = briefing.snapshot(tmp_path, NOW)
    assert [c["seat"] for c in data["cards"]] == ["recent", "old"]
    assert data["cards"][1]["age_seconds"] == 3600
    assert "stale snapshot" in briefing.render(data)


@pytest.mark.parametrize("body", [
    {"seat": "../escape"}, {"seat": ""}, {"seat": "s", "doing": 7},
    {"seat": "s", "doing": "x" * 1201}, {"seat": "s", "state": "live"},
])
def test_invalid_reports_do_not_write_files(tmp_path, monkeypatch, body):
    monkeypatch.delenv("MEGAZWORD_SEAT", raising=False)
    with pytest.raises(ValueError):
        briefing.publish(body, tmp_path)
    assert not (tmp_path / "briefings").exists()


def test_corrupt_cards_do_not_hide_valid_reports(tmp_path):
    briefing.publish({"seat": "valid", "doing": "test"}, tmp_path, NOW)
    folder = tmp_path / "briefings"
    (folder / "broken.json").write_text("{", encoding="utf-8")
    (folder / "bad-schema.json").write_text("[]", encoding="utf-8")
    (folder / "oversize.json").write_text("x" * 20001, encoding="utf-8")
    data = briefing.snapshot(tmp_path, NOW)
    assert len(data["cards"]) == 1 and data["unreadable"] == 3


def test_reports_scrub_tokens_and_terminal_controls(tmp_path):
    briefing.publish({"seat": "safe", "doing": "API_KEY=secret-value\x1b\x9b\x7f"}, tmp_path, NOW)
    text = (tmp_path / "briefings" / "safe.json").read_text(encoding="utf-8")
    assert "secret-value" not in text
    assert "removed by Mega Zword" in text
    assert "\\u001b" not in text and "\\u009b" not in text and "\\u007f" not in text


def test_separate_sessions_publish_concurrently(tmp_path):
    with ThreadPoolExecutor(max_workers=4) as workers:
        list(workers.map(lambda n: briefing.publish(
            {"seat": f"seat-{n}", "doing": str(n)}, tmp_path, NOW), range(12)))
    data = briefing.snapshot(tmp_path, NOW)
    assert len(data["cards"]) == 12 and data["unreadable"] == 0
    assert {c["doing"] for c in data["cards"]} == {str(n) for n in range(12)}


def test_cli_reports_and_shows_without_backend_or_config_loading(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setenv("MEGAZWORD_SEAT", "Testlog-14")
    monkeypatch.setattr(config, "load", lambda: pytest.fail("briefings do not need model config"))
    assert cli.main(["brief", "report", "--doing", "test", "--next", "publish"]) == 0
    assert cli.main(["brief"]) == 0
    output = capsys.readouterr().out
    assert "Saved report for testlog-14" in output and "Next: publish" in output


def test_mcp_status_writes_card_without_room_message(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    result = mcp_hive.handle({"id": 1, "method": "tools/call", "params": {
        "name": "hive_status", "arguments": {"seat": "Testlog-14", "done": "tests passed"}}})
    assert result["result"]["isError"] is False
    assert briefing.snapshot(tmp_path)["cards"][0]["done"] == "tests passed"
    assert not (tmp_path / "rooms").exists()


@pytest.mark.parametrize("code", [0, 1])
def test_cli_job_lifecycle_reports_facts_without_claiming_verified_work(
    tmp_path, monkeypatch, code,
):
    from types import SimpleNamespace
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setenv("MEGAZWORD_SEAT", "worker-14")

    @briefing.track_run
    def run(sent, prompt, chain, cfg, memory, rating, forced):
        card = briefing.snapshot()["cards"][0]
        assert card["state"] == "working" and card["doing"] == "Fix the log"
        return code

    assert run("sent", "Fix the log", [], None, SimpleNamespace(project="mega-zword"),
               None, False) == code
    card = briefing.snapshot()["cards"][0]
    assert card["state"] == ("done" if code == 0 else "blocked")
    assert card["doing"] == ""
    assert "verify" in card["next"] if code == 0 else "retry" in card["next"]


def test_interrupted_job_leaves_honest_card_and_reraises(tmp_path, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(config, "HOME", tmp_path)

    @briefing.track_run
    def run(*args):
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        run("sent", "Task", [], None, SimpleNamespace(project="mega-zword"), None, False)
    card = briefing.snapshot()["cards"][0]
    assert card["state"] == "blocked" and "interrupted" in card["blocked"]


def test_unwritable_status_does_not_fail_the_job(tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace
    monkeypatch.setattr(briefing, "publish", lambda body: (_ for _ in ()).throw(OSError()))

    @briefing.track_run
    def run(*args):
        return 0

    assert run("sent", "Task", [], None, SimpleNamespace(project="mega-zword"), None, False) == 0
    assert "could not save session report: OSError" in capsys.readouterr().err


def test_brief_survives_a_redirected_cp1252_console(tmp_path, monkeypatch):
    """A redirected Windows console is cp1252; a card with an emoji or arrow must
    not crash `megazword brief` (it used to raise UnicodeEncodeError)."""
    monkeypatch.setattr(config, "HOME", tmp_path)
    briefing.publish({"seat": "emoji", "doing": "ship it 😀 → done", "next": "push"}, tmp_path, NOW)
    sink = io.BytesIO()
    stream = io.TextIOWrapper(sink, encoding="cp1252")
    monkeypatch.setattr(cli.sys, "stdout", stream)
    assert cli.main(["brief"]) == 0
    stream.flush()
    written = sink.getvalue()
    assert b"emoji" in written and b"\x3f" in written  # unencodable chars became '?'
