import json
from datetime import datetime, timezone

from megazword.routing import tencent_first


def test_tencent_models_lead_and_least_logged_tokens_go_first(tmp_path):
    log = tmp_path / "log.jsonl"
    now = datetime.now(timezone.utc).isoformat()
    log.write_text("\n".join(json.dumps({
        "backend": name, "time": now, "ok": True, "requests": 1,
        "est_tokens": tokens,
    }) for name, tokens in (
        ("tencent-glm-5.3-flash", 100),
        ("tencent-glm-5.3", 20),
        ("tencent-kimi-k3", 50),
    )), encoding="utf-8")
    names = ["mistral", "tencent-glm-5.3-flash", "tencent-glm-5.3",
             "tencent-kimi-k2.7-code", "tencent-kimi-k3",
             "tencent-deepseek-v4-pro", "tencent-deepseek-v4-flash-vision-exp",
             "codex"]

    assert tencent_first(names, log) == [
        "tencent-kimi-k2.7-code", "tencent-deepseek-v4-pro",
        "tencent-deepseek-v4-flash-vision-exp", "tencent-glm-5.3", "tencent-kimi-k3",
        "tencent-glm-5.3-flash", "mistral", "codex",
    ]


def test_tencent_first_keeps_default_order_when_usage_is_tied(tmp_path):
    names = ["tencent-glm-5.3-flash", "openrouter", "tencent-kimi-k3",
             "tencent-glm-5.3", "tencent-kimi-k2.7-code",
             "tencent-deepseek-v4-pro", "tencent-deepseek-v4-flash-vision-exp"]
    assert tencent_first(names, tmp_path / "missing.jsonl") == [
        "tencent-glm-5.3-flash", "tencent-kimi-k3", "tencent-glm-5.3",
        "tencent-kimi-k2.7-code", "tencent-deepseek-v4-pro",
        "tencent-deepseek-v4-flash-vision-exp", "openrouter",
    ]
