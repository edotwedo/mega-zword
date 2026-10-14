import io
import json
import urllib.error
import urllib.request

import pytest

from megazword import cli, config
from megazword.backends import Backend, default_backends
from megazword.free_apis import OpenAICompatibleBackend


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "secret-test-credential")
    return OpenAICompatibleBackend("test", timeout=7, base_url="https://example.test/v1/",
                                   model="test-model", key_env="TEST_API_KEY")


def reply(content=" answer "):
    return io.BytesIO(json.dumps({"choices": [{"message": {"content": content}}]}).encode())


def test_request_and_answer(api, monkeypatch):
    def fake(request, timeout):
        assert request.full_url == "https://example.test/v1/chat/completions"
        assert request.get_method() == "POST"
        assert request.get_header("Authorization") == "Bearer secret-test-credential"
        assert request.get_header("Content-type") == "application/json"
        assert timeout == 7
        assert json.loads(request.data) == {
            "model": "test-model", "messages": [{"role": "user", "content": "hello ☃"}],
            "stream": False,
        }
        return reply()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert isinstance(api, Backend)
    result = api.run("hello ☃")
    assert result.ok and result.text == "answer"
    assert result.backend == "test" and result.seconds >= 0


@pytest.mark.parametrize("value", [None, "", "a-key"])
def test_available_without_network(api, monkeypatch, value):
    monkeypatch.delenv("TEST_API_KEY", raising=False)
    if value is not None:
        monkeypatch.setenv("TEST_API_KEY", value)
    def unexpected(*args, **kwargs):
        pytest.fail("must not contact HTTP without a key")
    monkeypatch.setattr(urllib.request, "urlopen", unexpected)
    assert api.available() == bool(value)
    if not value:
        result = api.run("hi")
        assert not result.ok and result.error == "API key not set"


@pytest.mark.parametrize("error, message", [
    (urllib.error.HTTPError("https://example.test", 429, "secret-test-credential", {},
                            io.BytesIO(b"secret-test-credential")), "API HTTP error 429: rate limited, try again in 2 minutes"),
    (TimeoutError("secret-test-credential"), "API request timed out"),
    (urllib.error.URLError(TimeoutError("secret-test-credential")), "API request timed out"),
    (urllib.error.URLError("secret-test-credential"),
     "API connection failed: unable to connect (network or DNS)"),
    (OSError("secret-test-credential"), "API request failed"),
])
def test_failures_are_safe_results(api, monkeypatch, error, message):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(urllib.request, "urlopen", fail)
    result = api.run("hi")
    assert not result.ok and result.text == "" and result.error == message
    assert "secret-test-credential" not in repr(result)


@pytest.mark.parametrize("code, word", [(401, "unauthorized"), (403, "forbidden")])
def test_auth_errors_are_plain_and_never_leak_key(api, monkeypatch, code, word):
    from megazword import failures
    body = json.dumps({"error": {"message": "Forbidden: key secret-test-credential "
                                            "has no access", "code": code}}).encode()
    def fail(*args, **kwargs):
        raise urllib.error.HTTPError(
            "https://example.test/v1/chat/completions?key=secret-test-credential", code,
            "Forbidden secret-test-credential", {"X-Key": "secret-test-credential"},
            io.BytesIO(body))
    monkeypatch.setattr(urllib.request, "urlopen", fail)
    result = api.run("hi")
    assert not result.ok and result.text == ""
    assert result.error.startswith(f"API HTTP error {code}: {word}")
    assert "auth" in result.error
    assert "Traceback" not in result.error
    assert "secret-test-credential" not in repr(result)
    assert failures.classify("groq", result.error).kind == "auth"


@pytest.mark.parametrize("body", [b"not json", b"{}", b'{"choices":[]}',
                                     b'{"choices":[{"message":{"content":null}}]}',
                                     b'{"choices":[{"message":{"content":" "}}]}'])
def test_invalid_response(api, monkeypatch, body):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: io.BytesIO(body))
    result = api.run("hi")
    assert not result.ok and "invalid or empty" in result.error


def test_echoed_key_is_redacted(api, monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: reply("secret-test-credential"))
    assert api.run("hi").text == "[REDACTED]"


@pytest.mark.parametrize("headers,minutes", [({}, 2), ({"Retry-After": "90"}, 2),
    ({"Retry-After": "180"}, 3), ({"Retry-After": "bad"}, 2),
    ({"Retry-After": "NaN"}, 2), ({"Retry-After": "30.5"}, 1)])
def test_api_rate_limit_reset(headers, minutes):
    from datetime import datetime, timedelta, timezone
    from megazword.free_apis import http_error_message
    from megazword.limits import detect
    now = datetime.now(timezone.utc)
    hit = detect(http_error_message(429, headers), now)
    assert hit.exact and hit.until == now + timedelta(minutes=minutes)


def test_retry_after_http_date():
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime
    from megazword.free_apis import http_error_message
    date = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=150))
    assert "in 3 minutes" in http_error_message(429, {"Retry-After": date})


def test_cloudflare_daily_quota_uses_utc_midnight_reset(api, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from megazword import free_apis
    from megazword.limits import detect

    api.name = "cloudflare"
    monkeypatch.setattr(free_apis, "_cloudflare_daily_reset_seconds", lambda: 3 * 60 * 60)
    body = {"errors": [{"code": 4006, "message":
                        "AiError: you have used up your daily free allocation of 10,000 neurons"}]}

    def fail(request, **kwargs):
        raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", {},
                                     io.BytesIO(json.dumps(body).encode()))

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    result = api.run("hi")
    assert not result.ok
    assert "daily free allocation exhausted; resets at 00:00 UTC" in result.error
    assert "try again in 180 minutes" in result.error
    now = datetime.now(timezone.utc)
    hit = detect(result.error, now)
    assert hit and hit.exact and hit.until == now + timedelta(hours=3)


def test_cloudflare_capacity_429_is_not_misread_as_daily_quota(api):
    from megazword import free_apis
    body = {"errors": [{"code": 3040, "message": "Capacity temporarily exceeded"}]}
    assert not free_apis._cloudflare_daily_quota_exhausted(json.dumps(body).encode())


def test_cloudflare_daily_reset_is_midnight_utc():
    from datetime import datetime, timezone
    from megazword.free_apis import _cloudflare_daily_reset_seconds
    now = datetime(2026, 10, 14, 22, 30, tzinfo=timezone.utc)
    assert _cloudflare_daily_reset_seconds(now) == 90 * 60


def test_mistral_1300_rate_limit_is_identified_without_echoing_body(api, monkeypatch):
    api.name = "mistral"
    body = {"object": "error", "message": "Rate limit exceeded",
            "type": "rate_limited", "code": 1300}

    def fail(request, **kwargs):
        raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", {},
                                     io.BytesIO(json.dumps(body).encode()))

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    result = api.run("hi")
    assert not result.ok
    assert "Mistral rate limit exceeded (code 1300)" in result.error
    assert "Rate limit exceeded" not in result.error


def test_cloudflare_validation_error_reason_is_safe(api, monkeypatch):
    api.name = "cloudflare"
    monkeypatch.setenv("OTHER_SECRET", "opaque-other-secret")
    seen = []
    def fail(request, **kwargs):
        seen.append(json.loads(request.data))
        body = {"errors": [{"message": "context too long secret-test-credential opaque-other-secret "
                    "https://private.test/?token=hidden\npassword: hunter42"}]}
        raise urllib.error.HTTPError(request.full_url, 400, "private", {},
                                     io.BytesIO(json.dumps(body).encode()))
    monkeypatch.setattr(urllib.request, "urlopen", fail)
    result = api.run("job")
    assert "context too long" in result.error
    for secret in ("secret-test-credential", "opaque-other-secret", "private.test", "hunter42"):
        assert secret not in result.error
    assert "stream" not in seen[0]
    assert len(result.error) < 270 and "\n" not in result.error


def test_presets_config_and_routes(monkeypatch):
    config.HOME.mkdir(parents=True)
    (config.HOME / "config.toml").write_text(
        '[free.openrouter]\nmodel = "custom:free"\n[free.groq]\nmodel = "custom-groq"\n')
    cfg = config.load()
    backends = default_backends()
    assert backends["openrouter"].model == "custom:free"
    assert backends["groq"].model == "custom-groq"
    assert backends["openrouter"].base_url == "https://openrouter.ai/api/v1"
    assert backends["groq"].base_url == "https://api.groq.com/openai/v1"
    assert backends["openrouter"].key_env == "OPENROUTER_API_KEY"
    assert backends["groq"].key_env == "GROQ_API_KEY"
    assert config.DEFAULT_FREE["openrouter"].endswith(":free")
    assert cfg.route == config.DEFAULT_ROUTE
    generated = config.render_default(list(backends))
    assert "openrouter" not in generated and "groq" not in generated
    assert {"openrouter", "groq"} <= default_backends(edit=True).keys()


@pytest.mark.parametrize("name, key_env", [("openrouter", "OPENROUTER_API_KEY"),
                                           ("groq", "GROQ_API_KEY")])
def test_cli_forced_and_edit_agent(name, key_env, monkeypatch, capsys):
    monkeypatch.setattr("megazword.ollama.reachable", lambda *a, **k: False)
    monkeypatch.setenv(key_env, "secret-test-credential")
    calls = []
    def fake(request, **kwargs):
        calls.append(json.loads(request.data))
        return reply()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    cfg = config.Config()
    cfg.free[name] = "override-model"
    assert cli.main(["run", "hello", "-m", name], cfg=cfg) == 0
    assert calls[0]["model"] == "override-model"
    assert "answer" in capsys.readouterr().out
    def finish_reply(request, **kwargs):
        calls.append(json.loads(request.data))
        return reply(json.dumps({"tool": "finish", "arguments": {"summary": "done"}}))
    monkeypatch.setattr(urllib.request, "urlopen", finish_reply)
    assert cli.main(["run", "hello", "-m", name, "--edit"], cfg=cfg) == 0
    assert "tools" in calls[-1]
    assert len(calls) == 2
    assert cli.main(["backends"], cfg=cfg) == 0
    output = capsys.readouterr().out
    assert "openrouter" in output and "groq" in output
    assert "secret-test-credential" not in output


NEW_FREE = ("cloudflare", "zai", "gemini-api", "nvidia", "mistral")


def test_b14_backends_exist_off_route_and_train_flags():
    backends = default_backends()
    for name in NEW_FREE:
        assert name in backends
        for level, names in config.DEFAULT_ROUTE.items():
            # B15 (Phil): only Mistral is routed by default, first in `easy`.
            assert name not in names or (name, level) == ("mistral", "easy")
        assert name in default_backends(edit=True)
    assert not backends["zai"].trains_on_data
    assert backends["gemini-api"].trains_on_data
    assert backends["mistral"].trains_on_data
    assert not backends["cloudflare"].trains_on_data
    assert not backends["nvidia"].trains_on_data
    assert not backends["openrouter"].trains_on_data


def test_cloudflare_needs_account_id_and_puts_it_in_url(monkeypatch):
    from megazword.free_apis import free_backends
    b = {x.name: x for x in free_backends(config.DEFAULT_FREE)}["cloudflare"]
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "secret-test-credential")
    assert not b.available()
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct123")
    assert b.available()
    seen = []

    def fake(request, timeout):
        seen.append(request.full_url)
        return reply()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    result = b.run("hello")
    assert result.ok
    assert seen[0] == ("https://api.cloudflare.com/client/v4/accounts/"
                       "acct123/ai/v1/chat/completions")


@pytest.mark.parametrize("name, key_env", [
    ("zai", "ZAI_API_KEY"),
    ("gemini-api", "GOOGLE_AI_API_KEY"),
    ("mistral", "MISTRAL_API_KEY"),
    ("nvidia", "NVIDIA_API_KEY"),
])
def test_new_free_forced_run(name, key_env, monkeypatch, capsys):
    monkeypatch.setenv(key_env, "secret-test-credential")
    def fake(request, **kwargs):
        return reply()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert cli.main(["run", "hello", "-m", name], cfg=config.Config()) == 0
    out = capsys.readouterr().out
    assert "answer" in out
    assert "secret-test-credential" not in out


@pytest.mark.parametrize("model", ['""', '123'])
def test_bad_model_config(tmp_path, model):
    path = tmp_path / "config.toml"
    path.write_text(f"[free.groq]\nmodel = {model}\n")
    with pytest.raises(ValueError, match="nonempty string"):
        config.load(path)


def test_provider_training_labels_match_developer_api_terms():
    backends = default_backends()
    # R1 records that Z.ai developer/API content is not used for training unless
    # the developer opts in. Consumer-plan terms are not the API terms.
    assert not backends["zai"].trains_on_data
    assert backends["gemini-api"].trains_on_data
    assert backends["mistral"].trains_on_data


def test_gemini_api_default_model_is_flash_latest():
    assert config.DEFAULT_FREE["gemini-api"] == "gemini-flash-latest"
    assert default_backends()["gemini-api"].model == "gemini-flash-latest"
