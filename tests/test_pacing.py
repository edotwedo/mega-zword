from datetime import datetime, timedelta, timezone

from megazword.pacing import (
    HARD_ONLY_THRESHOLD,
    PlanStatus,
    allowed,
    pace,
    project,
    rank,
    status,
    window_length,
)
from megazword.usage_sources import PlanUsage, Window


NOW = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)


def window(name, used, reset):
    return Window(name, used, reset)


def usage(service, *windows):
    return PlanUsage(service, list(windows), "fake")


def test_window_lengths_known_variants_and_unknown_fallback():
    assert window_length("5-hour") == (timedelta(hours=5), True)
    assert window_length("weekly") == (timedelta(days=7), True)
    assert window_length("weekly (Opus)") == (timedelta(days=7), True)
    assert window_length("iguana_necktie") == (timedelta(days=7), False)
    assert window_length("extra_usage") == (timedelta(days=7), False)


def test_pace_compares_usage_with_elapsed_window_time():
    assert pace(window("5-hour", 50, NOW + timedelta(hours=2, minutes=30)), NOW) == 0
    assert pace(window("weekly", 75, NOW + timedelta(days=3, hours=12)), NOW) == 25
    assert pace(window("weekly", 25, NOW + timedelta(days=3, hours=12)), NOW) == -25


def test_pace_clamps_elapsed_time_and_handles_missing_or_naive_reset():
    assert pace(window("5-hour", 50, NOW + timedelta(hours=7)), NOW) == 50
    assert pace(window("weekly", 50, None), NOW) == 0
    naive_reset = (NOW + timedelta(hours=2, minutes=30)).replace(tzinfo=None)
    assert pace(window("5-hour", 25, naive_reset), NOW) == -25


def test_status_uses_worst_pace_max_usage_and_marks_unknown_names():
    result = status(usage(
        "claude",
        window("5-hour", 25, NOW + timedelta(hours=2, minutes=30)),
        window("weekly (Opus)", 60, NOW + timedelta(days=3, hours=12)),
        window("iguana_necktie", 20, NOW + timedelta(days=3, hours=12)),
    ), NOW)
    assert result.service == "claude"
    assert result.worst_pace == 10
    assert result.max_used_percent == 60
    assert result.verdict == "free"
    assert result.unknown_windows == ["iguana_necktie"]


def test_status_verdict_thresholds_and_empty_service():
    over = status(usage("codex", window("weekly", 61,
                                         NOW + timedelta(days=3, hours=12))), NOW)
    out = status(usage("claude", window("5-hour", 95, NOW)), NOW)
    empty = status(usage("grok"), NOW)
    assert over.worst_pace == 11
    assert over.verdict == "hard-only"
    assert HARD_ONLY_THRESHOLD == 10
    assert out.verdict == "out"
    assert empty.verdict == "unknown"


def test_allowed_by_verdict_and_rating():
    out = PlanStatus("out", 0, 95, "out", [])
    hard_only = PlanStatus("limited", 11, 40, "hard-only", [])
    free = PlanStatus("free", -10, 20, "free", [])
    unknown = PlanStatus("unknown", 0, 0, "unknown", [])
    assert not allowed(out, "hard")
    assert not allowed(hard_only, "easy")
    assert allowed(hard_only, "hard")
    assert allowed(free, "easy")
    assert allowed(unknown, "medium")


def test_rank_filters_and_keeps_cheapest_first():
    statuses = {
        "ahead": PlanStatus("ahead", 20, 70, "hard-only", []),
        "steady": PlanStatus("steady", -5, 50, "free", []),
        "mystery": PlanStatus("mystery", 0, 0, "unknown", []),
        "empty": PlanStatus("empty", 0, 99, "out", []),
        "expiring": PlanStatus("expiring", -30, 20, "free", [], burn=True),
    }
    names = ["steady", "mystery", "empty", "ahead", "expiring"]
    assert rank(statuses, names, "easy", NOW) == ["expiring", "steady", "mystery"]
    assert rank(statuses, names, "hard", NOW) == ["expiring", "steady", "mystery", "ahead"]


def test_burn_only_near_reset_with_leftover():
    soon = usage("a", window("5-hour", 30, NOW + timedelta(minutes=30)))
    later = usage("b", window("5-hour", 30, NOW + timedelta(hours=3)))
    at_reserve = usage("c", window("5-hour", 91, NOW + timedelta(minutes=30)))
    assert status(soon, NOW).burn
    assert not status(later, NOW).burn
    assert not status(at_reserve, NOW).burn


def test_reserve_depends_on_the_window():
    five = status(usage("a", window("5-hour", 90, NOW + timedelta(hours=2))), NOW)
    weekly_keep = status(usage("b", window("weekly", 90, NOW + timedelta(days=3))), NOW)
    weekly_stop = status(usage("c", window("weekly", 95, NOW + timedelta(days=3))), NOW)
    assert five.verdict == "out"
    assert weekly_keep.verdict != "out"
    assert weekly_stop.verdict == "out"


def test_rank_preserves_candidate_order_for_equal_pace():
    same = PlanStatus("same", -5, 40, "free", [])
    assert rank({"a": same, "b": same}, ["b", "a"], "medium") == ["b", "a"]


def test_monthly_is_a_known_window_with_a_ten_percent_reserve():
    assert window_length("monthly") == (timedelta(days=30), True)
    assert status(usage("cmdc", window("monthly", 85, NOW + timedelta(days=20))), NOW).verdict != "out"
    assert status(usage("cmdc", window("monthly", 91, NOW + timedelta(days=20))), NOW).verdict == "out"


def test_over_pace_but_not_at_reserve_is_a_soft_throttle():
    # 19% used, 27 of 30 days left: ahead of the clock, far from the floor.
    result = status(usage("cmdc", window("monthly", 19, NOW + timedelta(days=27))), NOW)
    assert result.verdict == "throttle"
    assert allowed(result, "easy") and allowed(result, "hard")  # never a hard block


def test_project_dates_the_dry_out_and_clamps_when_it_outlasts_the_reset():
    gap = project(window("monthly", 19, NOW + timedelta(days=27)), NOW)
    assert gap is not None and 13 <= gap <= 15
    # 2% used is too little to extrapolate: no projection, which the guard treats as no gap.
    assert project(window("5-hour", 2, NOW + timedelta(hours=3, minutes=18)), NOW) is None
    assert project(window("5-hour", 20, NOW + timedelta(hours=3, minutes=18)), NOW) == 0
    assert project(window("monthly", 19, NOW + timedelta(days=30)), NOW) is None  # fresh cycle
    assert project(window("weekly", 0, NOW + timedelta(days=3)), NOW) is None  # no usage yet


def test_a_hot_monthly_budget_throttles_but_never_hard_blocks():
    # 40% used, 2 of 30 days gone: far over the weekly threshold, but a month is not a 5-hour.
    result = status(usage("cmdc", window("monthly", 40, NOW + timedelta(days=28))), NOW)
    assert result.verdict == "throttle"
    assert allowed(result, "easy") and allowed(result, "hard")


def test_rank_sinks_a_throttled_plan_below_roomier_ones():
    statuses = {
        "cmdc": PlanStatus("cmdc", 6, 19, "throttle", []),
        "ovh": PlanStatus("ovh", -5, 30, "free", []),
        "claude": PlanStatus("claude", -10, 20, "free", []),
    }
    assert rank(statuses, ["cmdc", "claude", "ovh"], "easy", NOW) == ["claude", "ovh", "cmdc"]


def test_a_reading_from_before_the_reset_no_longer_blocks():
    from datetime import datetime, timedelta, timezone
    from megazword.pacing import status
    from megazword.usage_sources import PlanUsage, Window
    now = datetime(2026, 10, 18, 16, 0, tzinfo=timezone.utc)
    stale = PlanUsage("gemini", [Window("weekly", 100.0, now - timedelta(minutes=3))], "test")
    assert status(stale, now).verdict == "free"
    live = PlanUsage("gemini", [Window("weekly", 100.0, now + timedelta(days=6))], "test")
    assert status(live, now).verdict == "out"


def test_project_ignores_a_fresh_window_and_tiny_usage():
    # 2026-10-25: early bursts projected dry-outs while Phil's apps said "on track".
    assert project(window("weekly", 30, NOW + timedelta(days=6, hours=20)), NOW) is None  # ~2% in
    assert project(window("weekly", 5, NOW + timedelta(days=3)), NOW) is None  # under 10% used
    # Phil's real reading: 30% used with ~4.3 of 7 days left is on track, no gap.
    assert project(window("weekly", 30, NOW + timedelta(days=4, hours=8)), NOW) == 0
