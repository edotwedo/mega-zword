import json
from datetime import datetime, timedelta, timezone

from megazword.routing import spread


def _log(tmp_path, runs, when=None):
    log = tmp_path / "log.jsonl"
    stamp = (when or datetime.now(timezone.utc)).isoformat()
    log.write_text("\n".join(json.dumps({
        "backend": name, "time": stamp, "ok": True, "requests": count,
    }) for name, count in runs.items()), encoding="utf-8")
    return log


def test_least_used_free_source_goes_first_and_paid_stay_last(tmp_path):
    log = _log(tmp_path, {"groq": 3, "mistral": 1, "cloudflare": 2})
    names = ["groq", "codex", "mistral", "cloudflare", "zai", "claude"]
    assert spread(names, "easy", log) == [
        "zai", "mistral", "cloudflare", "groq", "codex", "claude"]


def test_finite_tencent_grants_get_a_quarter_share_outside_hard_work(tmp_path):
    # One Tencent request weighs like four free-tier requests.
    log = _log(tmp_path, {"tencent-kimi-k3": 1, "groq": 3, "mistral": 5})
    names = ["tencent-kimi-k3", "groq", "mistral"]
    assert spread(names, "medium", log) == ["groq", "tencent-kimi-k3", "mistral"]


def test_hard_work_leads_with_least_used_tencent_grant(tmp_path):
    log = _log(tmp_path, {"tencent-glm-5.3": 2, "tencent-kimi-k3": 1})
    names = ["groq", "tencent-glm-5.3", "tencent-kimi-k3", "claude"]
    assert spread(names, "hard", log) == [
        "tencent-kimi-k3", "tencent-glm-5.3", "groq", "claude"]


def test_ties_and_missing_log_keep_configured_order(tmp_path):
    names = ["mistral", "groq", "tencent-glm-5.3", "grok"]
    assert spread(names, "easy", tmp_path / "missing.jsonl") == names


def test_unused_tencent_waits_behind_unused_free_tiers_outside_hard_work(tmp_path):
    names = ["tencent-glm-5.3", "mistral", "groq"]
    missing = tmp_path / "missing.jsonl"
    assert spread(names, "easy", missing) == ["mistral", "groq", "tencent-glm-5.3"]
    assert spread(names, "hard", missing) == ["tencent-glm-5.3", "groq", "mistral"]


def test_only_the_last_24_hours_count(tmp_path):
    old = datetime.now(timezone.utc) - timedelta(hours=30)
    log = _log(tmp_path, {"groq": 50}, when=old)
    assert spread(["groq", "mistral"], "easy", log) == ["groq", "mistral"]


def test_small_models_share_easy_work_but_wait_behind_stronger_ones_otherwise(tmp_path):
    missing = tmp_path / "missing.jsonl"
    names = ["mistral", "groq", "nvidia", "zai"]
    assert spread(names, "easy", missing) == names
    assert spread(names, "medium", missing) == ["groq", "zai", "mistral", "nvidia"]
