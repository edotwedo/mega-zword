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
