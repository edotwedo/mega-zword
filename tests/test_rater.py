import json
import pytest

from megazword import rater
from megazword.ollama import generate as _real_generate  # noqa: F401  (ensure import works)


# Helpers
def make_json_obj(level: str, reason: str) -> str:
    return json.dumps({"rating": level, "reason": reason})


# ---------- rule_rate tests ----------

def test_rule_rate_short_easy():
    prompt = "hi"
    r = rater.rule_rate(prompt)
    assert r.level == "easy"
    assert r.source == "rule"
    assert r.reason == "short single-line prompt"


def test_rule_rate_multiline_medium():
    prompt = "line1\nline2"
    r = rater.rule_rate(prompt)
    assert r.level == "medium"
    assert r.source == "rule"
    assert r.reason == "default for mid-size prompts"


def test_rule_rate_hard_keyword():
    prompt = "please refactor this module"
    r = rater.rule_rate(prompt)
    assert r.level == "hard"
    assert r.source == "rule"
    assert "keyword" in r.reason or "long prompt" in r.reason

def test_rule_rate_long_prompt():
    prompt = "x" * 2500
    r = rater.rule_rate(prompt)
    assert r.level == "hard"
    assert r.source == "rule"


# ---------- rate(): valid local rating ----------

def test_rate_valid_local_easy(monkeypatch):
    def fake_generate(prompt_text, model, json_format=None, timeout=None):
        assert "Request:" in prompt_text
        return make_json_obj("easy", "trivial")

    monkeypatch.setattr(rater.ollama, "generate", fake_generate)
    r = rater.rate("Hello world", model="test-model")
    assert r.level == "easy"
    assert r.reason == "trivial"
    assert r.source == "local:test-model"


def test_rate_valid_local_medium(monkeypatch):
    def fake_generate(prompt_text, model, json_format=None, timeout=None):
        return make_json_obj("medium", "ok task")

    monkeypatch.setattr(rater.ollama, "generate", fake_generate)
    prompt = "Write a function that adds two numbers.\nHandle edge cases."
    r = rater.rate(prompt, model="my-model")
    assert r.level == "medium"
    assert r.reason == "ok task"
    assert r.source == "local:my-model"


def test_rate_valid_local_hard(monkeypatch):
    def fake_generate(prompt_text, model, json_format=None, timeout=None):
        return make_json_obj("hard", "complex system")

    monkeypatch.setattr(rater.ollama, "generate", fake_generate)
    prompt = "Design a scalable architecture for background jobs."
    r = rater.rate(prompt)
    assert r.level == "hard"
    assert r.reason == "complex system"
    assert r.source == f"local:{rater.DEFAULT_RATER_MODEL}"


# ---------- rate(): hardcoded rule raises eary never lowers hard ----------

def test_rate_rule_raises_easy_to_hard(monkeypatch):
    def fake_generate(prompt_text, model, json_format=None, timeout=None):
        return make_json_obj("easy", "seems simple")

    monkeypatch.setattr(rater.ollama, "generate", fake_generate)
    # Contains a hard keyword: "refactor"
    prompt = "Refactor the entire database layer"
    r = rater.rate(prompt)
    assert r.level == "hard"
    assert "raised by rule" in r.reason
    assert r.source.endswith("+rule")


def test_rate_rule_never_lowers_hard(monkeypatch):
    def fake_generate(prompt_text, model, json_format=None, timeout=None):
        return make_json_obj("hard", "already hard")

    monkeypatch.setattr(rater.ollama, "generate", fake_generate)
    # Contains hard keyword
    prompt = "Design a concurrent cache system"
    r = rater.rate(prompt)
    assert r.level == "hard"
    # Should NOT have been modified by rule since local said hard
    assert r.reason == "already hard"
    assert r.source == f"local:{rater.DEFAULT_RATER_MODEL}"


# ---------- rate(): fallback on exceptions ----------

def test_rate_fallback_invalid_json(monkeypatch):
    def fake_generate(prompt_text, model, json_format=None, timeout=None):
        return "not valid json {{{{"

    monkeypatch.setattr(rater.ollama, "generate", fake_generate)
    prompt = "Hello friend"
    r = rater.rate(prompt)
    # Should fall back to rule_rate
    expected = rater.rule_rate(prompt)
    assert r.level == expected.level
    assert "local rater unavailable" in r.reason
    assert r.source == "rule"


def test_rate_fallback_invalid_rating(monkeypatch):
    def fake_generate(prompt_text, model, json_format=None, timeout=None):
        return make_json_obj("impossible", "weird")

    monkeypatch.setattr(rater.ollama, "generate", fake_generate)
    prompt = "Test the invalid rating path here."
    r = rater.rate(prompt)
    expected = rater.rule_rate(prompt)
    assert r.level == expected.level
    assert "local rater unavailable" in r.reason
    assert r.source == "rule"


def test_rate_fallback_model_exception(monkeypatch):
    def fake_generate(prompt_text, model, json_format=None, timeout=None):
        raise ConnectionError("model not found")

    monkeypatch.setattr(rater.ollama, "generate", fake_generate)
    prompt = "Just a simple test question"
    r = rater.rate(prompt)
    expected = rater.rule_rate(prompt)
    assert r.level == expected.level
    assert "ConnectionError" in r.reason
    assert r.source == "rule"


# ---------- prompt truncation test ----------

def test_rate_prompt_truncation_to_4000(monkeypatch):
    captured = {}

    def fake_generate(prompt_text, model, json_format=None, timeout=None):
        captured['prompt_text'] = prompt_text
        # Find the "Request:\n" prefix and get the actual request part
        idx = prompt_text.find("Request:\n")
        if idx != -1:
            captured['request_part'] = prompt_text[idx + len("Request:\n"):]
        return make_json_obj("easy", "truncated ok")

    monkeypatch.setattr(rater.ollama, "generate", fake_generate)

    # Create a prompt longer than 4000 chars
    long_prompt = "A" * 5000
    r = rater.rate(long_prompt)
    # rule_rate raises prompts longer than 2000 chars to hard
    assert r.level == "hard"
    assert "raised by rule" in r.reason
    assert r.source.endswith("+rule")
    # The request part passed to the model should be truncated to 4000 chars
    assert len(captured['request_part']) == 4000
    assert captured['request_part'] == "A" * 4000


def test_rate_prompt_not_truncated_under_limit(monkeypatch):
    captured = {}

    def fake_generate(prompt_text, model, json_format=None, timeout=None):
        captured['prompt_text'] = prompt_text
        idx = prompt_text.find("Request:\n")
        if idx != -1:
            captured['request_part'] = prompt_text[idx + len("Request:\n"):]
        return make_json_obj("medium", "fine")

    monkeypatch.setattr(rater.ollama, "generate", fake_generate)

    prompt = "Hello, this is a normal length prompt."
    r = rater.rate(prompt)
    assert r.level == "medium"
    # Should be exactly the prompt, not truncated
    assert captured['request_part'] == prompt


# ---------- custom model test ----------

def test_rate_uses_custom_model(monkeypatch):
    captured_models = []

    def fake_generate(prompt_text, model, json_format=None, timeout=None):
        captured_models.append(model)
        return make_json_obj("easy", "custom model test")

    monkeypatch.setattr(rater.ollama, "generate", fake_generate)
    r = rater.rate("Custom model prompt", model="custom:latest")
    assert captured_models == ["custom:latest"]
    assert r.source == "local:custom:latest"
