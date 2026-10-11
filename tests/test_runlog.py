import json
from datetime import datetime, timedelta, timezone

from megazword.runlog import summarize


def test_summary_skips_bad_lines_and_filters_window(tmp_path):
    now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
    path = tmp_path / "log.jsonl"
    records = [
        {"time": now.isoformat(), "backend": "grok", "ok": True,
         "seconds": 2.5, "prompt_chars": 4, "answer_chars": 8},
        {"time": now.isoformat(), "backend": "grok", "ok": False,
         "rejected": "empty", "seconds": 1, "prompt_chars": 3, "answer_chars": 0},
        {"time": (now - timedelta(days=2)).isoformat(), "backend": "grok", "ok": True},
    ]
    path.write_text("\n".join(json.dumps(row) for row in records) + "\nnot json\n")
    result = summarize(path, timedelta(hours=24), now)["grok"]
    assert (result.runs, result.ok, result.rejected, result.failed) == (2, 1, 1, 0)  # a rejection isn't also a failure
    assert (result.seconds, result.prompt_chars, result.answer_chars) == (3.5, 7, 8)


def test_summary_missing_log_is_empty(tmp_path):
    assert summarize(tmp_path / "missing", timedelta(days=1)) == {}


def test_token_totals_include_all_outcomes_and_legacy_zero(tmp_path):
    now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
    rows = [
        {"backend": "claude", "ok": True, "est_tokens": 7},
        {"backend": "claude", "ok": False, "rejected": "empty", "est_tokens": 2},
        {"backend": "claude", "ok": False, "est_tokens": 3},
        {"backend": "claude", "ok": True, "prompt_chars": 400, "answer_chars": 800},
        {"backend": "codex", "ok": True, "est_tokens": 5},
        {"backend": "grok", "ok": True},
    ]
    rows = [dict(time=now.isoformat(), **row) for row in rows]
    rows.extend([
        dict(time=(now - timedelta(days=2)).isoformat(), backend="claude", est_tokens=999),
        dict(time=(now + timedelta(hours=1)).isoformat(), backend="claude", est_tokens=999),
    ])
    path = tmp_path / "log.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    totals = summarize(path, timedelta(hours=24), now)
    assert {name: item.est_tokens for name, item in totals.items()} == {
        "claude": 12, "codex": 5, "grok": 0}
