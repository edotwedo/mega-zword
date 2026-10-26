"""megazword stats: per-day, per-AI numbers from a fake log."""

import json
from datetime import date, datetime, timedelta

from megazword import config
from megazword.cli import main
from megazword.stats import daily, table, trend

TODAY = date(2026, 10, 11)


def at(day: date, hour: int = 12) -> str:
    return datetime(day.year, day.month, day.day, hour).astimezone().isoformat()


def write_log(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n", encoding="utf-8")


def sample(path):
    y = TODAY - timedelta(days=1)
    write_log(path, [
        {"time": at(TODAY), "backend": "claude", "ok": True, "seconds": 4, "est_tokens": 100},
        {"time": at(TODAY), "backend": "claude", "ok": False, "rejected": "empty answer",
         "seconds": 2, "est_tokens": 10},
        {"time": at(y), "backend": "grok", "ok": True, "seconds": 6},
        {"time": at(TODAY - timedelta(days=9)), "backend": "grok", "ok": True},  # too old
    ])


def test_daily_groups_and_rates(tmp_path):
    p = tmp_path / "log.jsonl"
    sample(p)
    stats = daily(p, 7, TODAY)
    assert [(s.day, s.backend, s.runs) for s in stats] == [
        ("2026-10-10", "grok", 1), ("2026-10-11", "claude", 2)]
    c = stats[1]
    assert (c.ok_rate, c.escalation_rate, c.avg_seconds, c.est_tokens) == (0.5, 0.5, 3.0, 110)


def test_trend_fills_empty_days(tmp_path):
    p = tmp_path / "log.jsonl"
    sample(p)
    t = trend(p, 7, TODAY)
    assert len(t) == 7 and t[0]["runs"] == {} and t[-1]["runs"] == {"claude": 2}
    assert t[-2]["ok"] == {"grok": 1}


def test_table_and_empty(tmp_path):
    p = tmp_path / "log.jsonl"
    sample(p)
    text = table(daily(p, 7, TODAY))
    assert "claude" in text and "total" in text and "esc%" in text
    assert max(len(line) for line in text.splitlines()) <= 60
    assert "no runs" in table([])


def test_cli_stats(tmp_path, capsys):
    cfg = config.Config(log_path=tmp_path / "log.jsonl")
    assert main(["stats", "--days", "3"], {}, cfg) == 0
    assert "no runs" in capsys.readouterr().out


def test_dashboard_state_has_trend(tmp_path):
    from megazword.dashboard import App
    app = App(config.Config(log_path=tmp_path / "log.jsonl"), "p", backends={})
    assert len(app.state()["trend"]) == 7


def test_cli_stats_free(tmp_path, capsys):
    cfg = config.Config(log_path=tmp_path / "log.jsonl")
    sample(tmp_path / "log.jsonl")
    assert main(["stats", "--days", "30", "--free"], {}, cfg) == 0
    out = capsys.readouterr().out
    assert "FREE MODELS TOTAL" in out
    assert "SUB/PAID TOTAL" in out
    assert "claude" in out
