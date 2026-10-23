"""The guard line must say OUT when a plan is spent, not bury it as a mild gap.

Gemini's weekly limit was missed on 2026-10-23 because a spent plan that also had a gap was
reported only as "over pace - dry in ~5d"; nothing in the line said the plan was gone.
"""

from megazword import usage_guard


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
