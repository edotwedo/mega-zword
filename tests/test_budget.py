"""Cheap paid tier: $1/month cap read live from OpenRouter, fail closed."""

import json
import urllib.request

import pytest

from megazword import budget, config, routing
from megazword.backends import default_backends
from megazword.free_apis import CheapBackend


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    return tmp_path


def test_room_under_and_over_cap():
    assert budget.room(lambda: 0.10) == (True, "$0.10 of $1.00 this month")
    budget._path().unlink()
    ok, why = budget.room(lambda: 0.99)
    assert not ok and "reached" in why
    assert budget.known_exhausted()


def test_room_fails_closed_on_error():
    def broken():
        raise OSError("offline")
    ok, why = budget.room(broken)
    assert not ok and "unknown" in why


def test_cap_override_and_cache(home):
    (home / "budget.json").write_text(json.dumps({"monthly_usd": 2}), encoding="utf-8")
    assert budget.cap() == 2
    calls = []
    budget.spend(lambda: calls.append(1) or 1.5)
    assert budget.spend(lambda: calls.append(1) or 9.0) == 1.5  # cached
    assert calls == [1]
    assert budget.room()[0]  # $1.50 of $2.00
    assert "1.50 of $2.00" in budget.line()


def test_cheap_backend_refuses_when_budget_reached(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-test-credential")
    backend = default_backends()["cheap-deepseek-flash"]
    assert isinstance(backend, CheapBackend) and backend.available()
    monkeypatch.setattr(budget, "_fetch_spend", lambda: 1.0)
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("called model")))
    with pytest.raises(RuntimeError, match="budget reached"):
        backend.chat([{"role": "user", "content": "hi"}])
    assert not backend.available()


def test_cheap_backend_sends_price_ceiling(monkeypatch):
    import io
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-test-credential")
    monkeypatch.setattr(budget, "_fetch_spend", lambda: 0.0)
    seen = []

    def fake(request, timeout):
        seen.append(json.loads(request.data))
        return io.BytesIO(json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    backend = default_backends()["cheap-deepseek-pro"]
    assert backend.run("hi").text == "ok"
    assert seen[0]["model"] == "deepseek/deepseek-v4-pro"
    assert seen[0]["provider"] == {"max_price": {"prompt": 0.30, "completion": 0.60}}


def test_spread_puts_cheap_after_free_before_paid(tmp_path):
    names = ["claude", "cheap-deepseek-flash", "cheap-deepseek-pro", "groq", "zai"]
    log = tmp_path / "log.jsonl"
    assert routing.spread(names, "hard", log)[-3:] == ["cheap-deepseek-pro", "cheap-deepseek-flash", "claude"]
    assert routing.spread(names, "medium", log)[-3:] == ["cheap-deepseek-flash", "cheap-deepseek-pro", "claude"]
    assert set(routing.spread(names, "medium", log)[:2]) == {"groq", "zai"}


def test_cheap_models_are_routed_only_for_medium_and_hard():
    assert not any(n.startswith("cheap-") for n in config.DEFAULT_ROUTE["easy"])
    assert config.DEFAULT_ROUTE["medium"].count("cheap-deepseek-flash") == 1
    assert {"cheap-deepseek-flash", "cheap-deepseek-pro"} <= set(config.DEFAULT_ROUTE["hard"])
    assert config.DEFAULT_FREE_FAILOVER[-2:] == ["cheap-deepseek-flash", "cheap-deepseek-pro"]
