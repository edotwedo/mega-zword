"""One meter summary everywhere: out beats a bar, snapshot age, staleness."""

import json
from datetime import datetime, timedelta, timezone

from megazword import config, start, usage_sources
from megazword.meters import summarize, summarize_all
from megazword.usage_sources import PlanUsage, Window

NOW = datetime(2026, 10, 11, 9, tzinfo=timezone.utc)


def plan(name="codex", used=99, as_of=None, extra=()):
    return PlanUsage(name, [Window("5-hour", used, None), *extra], "x", as_of=as_of)


def test_out_beats_the_meter():
    s = summarize(plan(), {"codex": NOW + timedelta(hours=1)}, NOW)
    assert s.state == "out" and s.line().startswith("codex   out until ")
    assert "[" not in s.line()


def test_expired_out_mark_shows_the_meter_again():
    s = summarize(plan(used=40), {"codex": NOW - timedelta(minutes=1)}, NOW)
    assert s.state == "meter" and "40% 5-hour" in s.line()


def test_snapshot_age_and_stale():
    fresh = summarize(plan(as_of=NOW - timedelta(minutes=20)), {}, NOW)
    old = summarize(plan(as_of=NOW - timedelta(hours=2)), {}, NOW)
    assert "(as of " in fresh.line() and "stale" not in fresh.line()
    assert old.stale and old.line().endswith(", stale)")


def test_credit_windows_never_count_as_the_worst():
    s = summarize(PlanUsage("claude", [Window("5-hour", 30, None),
                                       Window("iguana_necktie", 99, None)], "x"), {}, NOW)
    assert s.used == 30


def test_out_without_any_meter_still_listed():
    found = summarize_all([plan("claude", 10)], {"grok": NOW + timedelta(days=3)}, NOW)
    assert [s.service for s in found] == ["claude", "grok"] and found[1].state == "out"


def test_codex_skips_empty_snapshot_from_a_failed_run(tmp_path, monkeypatch):
    day = tmp_path / ".codex" / "sessions" / "2026" / "10" / "11"
    day.mkdir(parents=True)
    good = {"payload": {"rate_limits": {"primary": {"used_percent": 99, "window_minutes": 300}}}}
    empty = {"payload": {"rate_limits": {"limit_id": "codex", "primary": None, "secondary": None}}}
    (day / "a-good.jsonl").write_text(json.dumps(good) + "\n")
    newer = day / "b-failed.jsonl"
    newer.write_text(json.dumps(empty) + "\n")
    import os
    os.utime(newer, (2e9, 2e9))  # newest file is the failed run
    monkeypatch.setattr(usage_sources, "HOME", tmp_path)
    p = usage_sources.codex()
    assert [(w.name, w.used_percent) for w in p.windows] == [("5-hour", 99.0)] and p.as_of


def test_start_screen_and_usage_say_the_same(tmp_path, monkeypatch, capsys):
    plans = [plan(as_of=NOW - timedelta(minutes=5)), plan("claude", 50)]
    cfg = config.Config(log_path=tmp_path / "l", out_until={"codex": NOW + timedelta(hours=1)})
    screen = start.render(cfg, plans, NOW, color=False)
    lines = {l.strip().split()[0]: l.strip() for l in summarize_all(plans, cfg.out_until, NOW)
             and [s.line() for s in summarize_all(plans, cfg.out_until, NOW)]}
    assert lines["codex"] in screen and lines["claude"] in screen


def test_dashboard_state_has_summaries(tmp_path):
    from megazword.dashboard import App, Usage
    app = App(config.Config(log_path=tmp_path / "l",
                            out_until={"codex": datetime.now(timezone.utc) + timedelta(hours=1)}),
              "p", usage=Usage(lambda: [plan(as_of=datetime.now(timezone.utc) - timedelta(hours=3))]),
              backends={})
    s = app.state()
    assert s["summaries"][0]["state"] == "out"
    assert s["usage"][0]["stale"] is True and s["usage"][0]["as_of"]
