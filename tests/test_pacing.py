from datetime import datetime, timedelta, timezone

from megazword.pacing import (
    HARD_ONLY_THRESHOLD,
    PlanStatus,
    allowed,
    pace,
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
    spent = usage("c", window("5-hour", 85, NOW + timedelta(minutes=30)))
    assert status(soon, NOW).burn
    assert not status(later, NOW).burn
    assert not status(spent, NOW).burn


def test_rank_preserves_candidate_order_for_equal_pace():
    same = PlanStatus("same", -5, 40, "free", [])
    assert rank({"a": same, "b": same}, ["b", "a"], "medium") == ["b", "a"]
