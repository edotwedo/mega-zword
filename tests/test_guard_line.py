"""The guard line must say OUT when a plan is spent, not bury it as a mild gap.

Gemini's weekly limit was missed on 2026-10-23 because a spent plan that also had a gap was
reported only as "over pace - dry in ~5d"; nothing in the line said the plan was gone.
"""

from datetime import datetime, timedelta, timezone

from megazword import usage_guard, usage_sources
from megazword.usage_sources import PlanUsage, Window


def _plan(service, verdict, used, gap, windows=()):
    return {"service": service, "verdict": verdict, "worst_pace": 0.0,
            "max_used_percent": used, "gap_days": gap, "gap_windows": list(windows)}


def test_a_spent_plan_is_reported_as_out_not_buried_as_a_gap():
    state = {"plans": [_plan("gemini", "out", 99.2, 5.0, ["weekly"])],
             "suggested_bias": "as-configured"}
    line = usage_guard._line(state)
    assert "gemini OUT" in line and "99%" in line
    assert "over pace" not in line  # a spent plan is not a warning


def test_a_gap_is_worded_as_days_before_the_reset():
    state = {"plans": [_plan("cmdc", "throttle", 40.0, 15.2, ["monthly"])]}
    line = usage_guard._line(state)
    assert "would run dry ~15d before its monthly reset" in line
    assert "dry in" not in line  # the old, misleading wording


def test_out_and_gap_plans_both_appear():
    state = {"plans": [_plan("gemini", "out", 99.2, 5.0, ["weekly"]),
                       _plan("codex", "free", 10.0, 3.0, ["weekly"])]}
    line = usage_guard._line(state)
    assert "STOP - gemini OUT" in line and "over pace: codex" in line


def test_nothing_wrong_is_a_silent_line():
    assert usage_guard._line({"plans": [_plan("claude", "free", 10.0, 0.0)]}) == ""


def test_the_line_names_the_window_the_gap_belongs_to_and_its_usage():
    # gap_windows sorts "5-hour" first; the old line labelled a weekly gap as a 5-hour one.
    plan = _plan("codex", "free", 40.0, 3.0, ["5-hour", "weekly"])
    plan.update(gap_window="weekly", gap_used_percent=40.0)
    line = usage_guard._line({"plans": [plan]})
    assert "codex weekly 40% used, would run dry ~3d before its weekly reset" in line
    assert "5-hour reset" not in line


def test_a_gap_under_half_a_day_is_not_posted():
    # "~0d" read as "empty now" while the plan sat at 30%.
    assert usage_guard._line({"plans": [_plan("claude", "free", 30.0, 0.4, ["weekly"])]}) == ""


def test_evaluate_names_the_window_that_actually_holds_the_gap(monkeypatch):
    """The fix for "a weekly gap printed as a 5-hour reset" lives in evaluate(), not in
    _line(), and the test above cannot catch a regression there: it injects gap_window
    directly, so it still passes if evaluate() goes back to gap_windows[0].

    gap_windows is sorted by NAME, so "5-hour" wins the list whenever it has any gap at all.
    Here the weekly window holds the far larger gap, so the 5-hour name must not be used.
    """
    now = datetime(2026, 10, 26, 0, 0, tzinfo=timezone.utc)
    usage = [PlanUsage("codex", [
        Window("5-hour", 85.0, now + timedelta(hours=2)),  # over pace: a small gap (~0.1d)
        Window("weekly", 60.0, now + timedelta(days=5)),   # over pace: a much bigger one (~3.7d)
    ], "test")]
    monkeypatch.setattr(usage_sources, "all_usage", lambda *a, **k: usage)

    plan = next(p for p in usage_guard.evaluate(now=now)["plans"] if p["service"] == "codex")
    # The trap is still in the data, which is exactly why the field exists.
    assert plan["gap_windows"] == ["5-hour", "weekly"]
    # The named window follows the largest gap, not the alphabetically first one.
    assert plan["gap_window"] == "weekly"
    assert plan["gap_used_percent"] == 60.0
