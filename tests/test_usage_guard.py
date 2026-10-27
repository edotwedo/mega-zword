"""The guard turns a monthly window running ahead of its clock into an early, automatic
hand-off: it projects the dry-out, marks the plan `throttle`, and posts one room line."""

import json
from datetime import datetime, timedelta, timezone

from megazword import config, usage_guard
from megazword.usage_sources import PlanUsage, Window

NOW = datetime(2026, 10, 23, 5, 0, tzinfo=timezone.utc)


def _cmdc(monthly=19, days_left=27):
    return PlanUsage("cmdc", [
        Window("5-hour", 2, NOW + timedelta(hours=3, minutes=18)),
        Window("weekly", 38, NOW + timedelta(days=2, hours=21)),
        Window("monthly", monthly, NOW + timedelta(days=days_left)),
    ], "test")


def test_evaluate_flags_the_monthly_gap_and_biases_to_free(monkeypatch):
    monkeypatch.setattr("megazword.usage_sources.all_usage", lambda log=None: [_cmdc()])
    state = usage_guard.evaluate(config.HOME, NOW)
    cmdc = next(plan for plan in state["plans"] if plan["service"] == "cmdc")
    assert cmdc["verdict"] == "throttle"
    assert 13 <= cmdc["gap_days"] <= 15
    assert "monthly" in cmdc["gap_windows"]
    assert state["throttled"] == ["cmdc"]
    assert state["suggested_bias"] == "free-first"


def test_run_posts_once_and_only_when_the_state_changes(monkeypatch):
    monkeypatch.setattr("megazword.usage_sources.all_usage", lambda log=None: [_cmdc()])
    sent = []
    monkeypatch.setattr("megazword.room.say",
                        lambda *a, **k: sent.append(a[1] if len(a) > 1 else k.get("text")))
    assert usage_guard.run(post=True, home_dir=config.HOME, now=NOW, write=lambda *_: None) == 0
    assert len(sent) == 1 and "over pace" in sent[0]
    # The same reading again: the state did not change, so nothing is posted.
    assert usage_guard.run(post=True, home_dir=config.HOME, now=NOW, write=lambda *_: None) == 0
    assert len(sent) == 1
    assert json.loads(usage_guard.state_path().read_text())["throttled"] == ["cmdc"]


def test_a_drifting_projection_does_not_repost(monkeypatch):
    # The dry-in figure moves a few tenths every run; whole-day rounding means a drift of
    # 0.3 days is not a state change, or the guard would post on every tick.
    readings = iter([[_cmdc(monthly=19, days_left=27)], [_cmdc(monthly=19.3, days_left=27)]])
    monkeypatch.setattr("megazword.usage_sources.all_usage", lambda log=None: next(readings))
    sent = []
    monkeypatch.setattr("megazword.room.say",
                        lambda *a, **k: sent.append(a[1] if len(a) > 1 else k.get("text")))
    assert usage_guard.run(post=True, home_dir=config.HOME, now=NOW, write=lambda *_: None) == 0
    assert len(sent) == 1
    assert usage_guard.run(post=True, home_dir=config.HOME, now=NOW, write=lambda *_: None) == 0
    assert len(sent) == 1  # the rounded line is unchanged, so nothing new is posted


def test_guard_stop_file_halts_runs(monkeypatch):
    stop = usage_guard.stop_path()
    stop.parent.mkdir(parents=True, exist_ok=True)
    stop.write_text("stop\n")
    called = []
    monkeypatch.setattr("megazword.usage_sources.all_usage", lambda log=None: called.append(1) or [])
    assert usage_guard.run(home_dir=config.HOME, now=NOW, write=lambda *_: None) == 0
    assert not called and not usage_guard.state_path().exists()


def test_a_healthy_plan_stays_quiet(monkeypatch):
    healthy = PlanUsage("claude", [Window("5-hour", 2, NOW + timedelta(hours=4, minutes=30))], "test")
    monkeypatch.setattr("megazword.usage_sources.all_usage", lambda log=None: [healthy])
    state = usage_guard.evaluate(config.HOME, NOW)
    assert state["throttled"] == [] and state["suggested_bias"] == "as-configured"
    assert usage_guard._line(state) == ""


def test_install_without_yes_only_prints_the_plan():
    lines = []
    assert usage_guard.install(every=30, yes=False, write=lines.append) == 0
    assert any(usage_guard.TASK_NAME in line for line in lines)


def test_linux_install_repeats_every_n_minutes(monkeypatch):
    import subprocess
    from megazword import night
    calls = []
    monkeypatch.setattr(night, "_ON_WINDOWS", False)
    monkeypatch.setattr(night, "_systemd", lambda action, name, files=None: calls.append(files)
                        or subprocess.CompletedProcess([action], 0, "", ""))
    assert usage_guard.install(every=30, yes=True, write=lambda s: None) == 0
    timer = calls[0]["megazword-guard.timer"]
    assert "OnActiveSec=1min" in timer and "OnUnitActiveSec=30min" in timer
