"""Grok's plan meter from the billing line in ~/.grok/logs/unified.jsonl (a fake home)."""

import json
from datetime import datetime, timezone

from megazword import usage_sources


def write_log(home, used, end, extra_lines=()):
    logs = home / ".grok" / "logs"
    logs.mkdir(parents=True)
    line = {"ts": "2026-10-11T06:29:44.798Z", "msg": usage_sources.GROK_BILLING_MSG,
            "ctx": {"config": {"creditUsagePercent": used,
                               "currentPeriod": {"type": "USAGE_PERIOD_TYPE_WEEKLY",
                                                 "start": "2026-10-04T23:17:31+00:00",
                                                 "end": end},
                               "billingPeriodEnd": end}}}
    rows = [json.dumps({"msg": "other"}), json.dumps(line), *extra_lines]
    (logs / "unified.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_reads_weekly_percent(tmp_path, monkeypatch):
    monkeypatch.setattr(usage_sources, "HOME", tmp_path)
    write_log(tmp_path, 95.0, "2026-10-11T23:17:31+00:00", ["not json"])
    plan = usage_sources.grok_billing(now=datetime(2026, 10, 11, 20, 0, tzinfo=timezone.utc))
    assert plan.source == "grok billing log" and plan.as_of is not None
    [w] = plan.windows
    assert w.name == "weekly" and w.used_percent == 95.0
    assert w.resets_at == datetime(2026, 10, 11, 23, 17, 31, tzinfo=timezone.utc)


def test_rolled_over_week_shows_fresh_start(tmp_path, monkeypatch):
    monkeypatch.setattr(usage_sources, "HOME", tmp_path)
    write_log(tmp_path, 95.0, "2026-10-11T23:17:31+00:00")
    plan = usage_sources.grok_billing(now=datetime(2026, 10, 11, 23, 30, tzinfo=timezone.utc))
    [w] = plan.windows
    assert w.used_percent == 0.0 and "new week" in plan.note
    assert w.resets_at == datetime(2026, 10, 18, 23, 17, 31, tzinfo=timezone.utc)


def test_no_log_falls_back_to_run_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(usage_sources, "HOME", tmp_path)
    assert usage_sources.grok_billing() is None
    plan = usage_sources.grok(tmp_path / "missing.jsonl")
    assert plan.source == "Mega Zword run log" and plan.windows == []
