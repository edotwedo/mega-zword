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
        assert request.get_header("User-agent") == "megazword/0.1.0b1"
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


def test_groq_gpt_oss_tool_requests_use_supported_reasoning_format(monkeypatch):
    from megazword import free_apis
    monkeypatch.setenv("TEST_API_KEY", "secret-test-credential")
    monkeypatch.setattr(free_apis, "_use_curl", lambda *args: False)
    groq = OpenAICompatibleBackend("groq", base_url="https://api.groq.com/openai/v1",
                                   model="openai/gpt-oss-20b", key_env="TEST_API_KEY")

    def fake(request, timeout):
        body = json.loads(request.data)
        assert body["tool_choice"] == "auto"
        assert body["reasoning_format"] == "parsed"
        assert body["tools"][0]["function"]["name"] == "finish"
        return io.BytesIO(json.dumps({"choices": [{"message": {
            "content": None, "tool_calls": [{"id": "t1", "type": "function",
                "function": {"name": "finish", "arguments": '{"summary":"ok"}'}}]}}]}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    message = groq.chat([{"role": "user", "content": "finish"}],
                        [{"type": "function", "function": {"name": "finish"}}])
    assert message["tool_calls"][0]["function"]["name"] == "finish"


def test_groq_curl_transport_keeps_key_out_of_arguments_and_tracks_limits(monkeypatch):
    from types import SimpleNamespace
    from megazword import free_apis

    monkeypatch.setenv("TEST_API_KEY", "secret-test-credential")
    monkeypatch.setattr(free_apis, "_use_curl", lambda name, *args: name == "groq")
    monkeypatch.setattr(free_apis, "_curl_bin", lambda: "curl.exe")
    recorded = []
    monkeypatch.setattr(free_apis, "_record_request_quota",
                        lambda *args: recorded.append(args))
    groq = OpenAICompatibleBackend("groq", timeout=7,
                                   base_url="https://api.groq.com/openai/v1",
                                   model="openai/gpt-oss-20b", key_env="TEST_API_KEY")

    def fake_run(args, **kwargs):
        assert "secret-test-credential" not in " ".join(args)
        assert "@-" in args
        header_path = args[args.index("-H") + 1][1:]
        assert "Bearer secret-test-credential" in open(header_path, encoding="utf-8").read()
        assert json.loads(kwargs["input"]) == {
            "model": "openai/gpt-oss-20b",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": False,
        }
        headers_path = args[args.index("-D") + 1]
        with open(headers_path, "w", encoding="utf-8") as handle:
            handle.write("HTTP/1.1 200 OK\r\nX-RateLimit-Remaining-Requests: 42\r\n"
                         "X-RateLimit-Limit-Requests: 60\r\n"
                         "X-RateLimit-Reset-Requests: 1m\r\n\r\n")
        return SimpleNamespace(returncode=0, stdout=reply().read())

    monkeypatch.setattr(free_apis.subprocess, "run", fake_run)
    message = groq.chat([{"role": "user", "content": "hello"}])
    assert message["content"] == " answer "
    assert groq.remaining_requests == 42 and groq.limit_requests == 60
    assert recorded == [("groq", 42, 60, "1m")]


def test_groq_curl_cloudflare_block_is_specific_and_secret_safe(monkeypatch):
    from types import SimpleNamespace
    from megazword import free_apis

    monkeypatch.setattr(free_apis, "_curl_bin", lambda: "curl.exe")

    def fake_run(args, **kwargs):
        headers_path = args[args.index("-D") + 1]
        with open(headers_path, "w", encoding="utf-8") as handle:
            handle.write("HTTP/1.1 403 Forbidden\r\n\r\n")
        return SimpleNamespace(returncode=0,
                               stdout=b"Error 1010: Access denied for Bearer secret")

    monkeypatch.setattr(free_apis.subprocess, "run", fake_run)
    with pytest.raises(free_apis.APIHTTPError) as caught:
        free_apis._curl_json_post("https://example.test", {}, {}, 5)
    assert str(caught.value) == \
        "API HTTP error 403: Cloudflare blocked this HTTP client (error 1010)"
    assert "Bearer secret" not in repr(caught.value)


def test_retry_after_accepts_lowercase_curl_header():
    from megazword.free_apis import retry_seconds
    assert retry_seconds({"retry-after": "37"}) == 37


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


def test_agent_harness_model_restriction_is_reported_as_access_not_bad_key(api, monkeypatch):
    from megazword import failures
    body = json.dumps({"error": {"message":
        "This model is only available on agentic harnesses. See https://openrouter.ai/apps"}}).encode()

    def fail(*args, **kwargs):
        raise urllib.error.HTTPError("https://example.test/chat/completions", 403,
                                     "Forbidden", {}, io.BytesIO(body))

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    result = api.run("synthetic probe")
    assert "only available on agentic harnesses" in result.error
    assert "https://" not in result.error
    failure = failures.classify("openrouter", result.error)
    assert failure.kind == "access"
    assert "restricted for this app" in failure.reason


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
    assert config.DEFAULT_FREE["openrouter"] == "openrouter/free"
    assert config.DEFAULT_FREE["mistral"] == "ministral-3b-2512"
    assert default_backends()["mistral"].model == "ministral-3b-2512"
    assert cfg.route == config.DEFAULT_ROUTE
    generated = config.render_default(list(backends))
    assert "openrouter" in generated and "groq" in generated
    assert {"openrouter", "groq"} <= default_backends(edit=True).keys()


@pytest.mark.parametrize("name, key_env", [("openrouter", "OPENROUTER_API_KEY"),
                                           ("groq", "GROQ_API_KEY")])
def test_cli_forced_and_edit_agent(name, key_env, monkeypatch, capsys):
    from megazword import free_apis
    monkeypatch.setattr("megazword.ollama.reachable", lambda *a, **k: False)
    monkeypatch.setattr(free_apis, "_use_curl", lambda *args: False)
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
    assert calls[-1]["tool_choice"] == "auto"
    assert len(calls) == 2
    assert cli.main(["backends"], cfg=cfg) == 0
    output = capsys.readouterr().out
    assert "openrouter" in output and "groq" in output
    assert "secret-test-credential" not in output


NEW_FREE = ("cloudflare", "zai", "zai-47", "gemini-api", "nvidia", "nvidia-lightning",
            "mistral", "tencent-glm-5.3-flash", "tencent-glm-5.3",
            "tencent-kimi-k2.7-code", "tencent-kimi-k3",
            "tencent-deepseek-v4-pro", "tencent-deepseek-v4-flash-vision-exp")


def test_free_backends_are_registered_and_routed_before_paid_plans():
    backends = default_backends()
    for name in NEW_FREE:
        assert name in backends
        for level, names in config.DEFAULT_ROUTE.items():
            assert name in names
        assert name in default_backends(edit=True)
    assert "ollama" in backends
    assert not backends["zai"].trains_on_data
    assert backends["gemini-api"].trains_on_data
    assert backends["mistral"].trains_on_data
    assert not backends["cloudflare"].trains_on_data
    assert not backends["nvidia"].trains_on_data
    assert not backends["nvidia-lightning"].trains_on_data
    assert backends["tencent"].model == "deepseek-v4-pro"
    assert backends["tencent"].key_env == "TENCENT_TOKENHUB_API_KEY"
    assert backends["tencent"].base_url == "https://tokenhub-intl.tencentcloudmaas.com/v1"
    assert backends["nvidia-lightning"].model == "nvidia/nemotron-3.5-lightning-30b-a3b"
    assert backends["nvidia-lightning"].key_env == backends["nvidia"].key_env
    assert backends["nvidia-lightning"].base_url == backends["nvidia"].base_url
    assert backends["zai-47"].model == "glm-4.7-flash"
    assert backends["zai-47"].key_env == backends["zai"].key_env
    assert backends["zai-47"].base_url == backends["zai"].base_url
    assert not backends["zai-47"].trains_on_data
    assert backends["openrouter"].trains_on_data
    assert "cerebras" in backends
    assert all("cerebras" not in names for names in config.DEFAULT_ROUTE.values())
    assert "cerebras" not in config.DEFAULT_FREE_FAILOVER
    assert {"groq-120b", "groq-qwen", "groq-allam"}.issubset(backends)
    assert "gemini-api-31-lite" in backends
    assert {"openrouter-dots", "openrouter-nemotron-nano",
            "openrouter-nemotron-lightning", "openrouter-laguna-s",
            "openrouter-laguna-xs"}.issubset(backends)
    assert all(name in config.DEFAULT_FREE_FAILOVER
               for name in ("groq-120b", "groq-qwen", "groq-allam"))


def test_groq_model_aliases_use_verified_ids_and_shared_key(monkeypatch):
    from megazword.free_apis import free_backends
    backends = {b.name: b for b in free_backends(config.DEFAULT_FREE)}
    expected = {"groq": "openai/gpt-oss-20b", "groq-120b": "openai/gpt-oss-120b",
                "groq-qwen": "qwen/qwen3.8-27b", "groq-allam": "allam-2-7b"}
    assert {name: backends[name].model for name in expected} == expected
    assert all(backends[name].key_env == "GROQ_API_KEY" for name in expected)
    assert all(backends[name].base_url == backends["groq"].base_url for name in expected)
    monkeypatch.setenv("GROQ_API_KEY", "secret-test-credential")
    assert all(backends[name].available() for name in expected)
    assert backends["gemini-api-31-lite"].model == "gemini-3.1-flash-lite"
    assert backends["gemini-api-31-lite"].key_env == backends["gemini-api"].key_env


def test_verified_openrouter_model_identities_keep_one_key_and_exact_free_ids():
    from megazword.free_apis import free_backends
    models = {"openrouter-dots": "dots-studio/dots-3-note-preview:free",
              "openrouter-nemotron-nano": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
              "openrouter-nemotron-lightning": "nvidia/nemotron-3.5-lightning:free",
              "openrouter-laguna-s": "poolside/laguna-s-2.1:free",
              "openrouter-laguna-xs": "poolside/laguna-xs-2.1:free"}
    backends = {b.name: b for b in free_backends(config.DEFAULT_FREE)}
    assert {name: backends[name].model for name in models} == models
    assert all(backends[name].key_env == "OPENROUTER_API_KEY" for name in models)
    assert all(backends[name].trains_on_data for name in models)
    assert all(name in config.DEFAULT_FREE_FAILOVER for name in models)


def test_nvidia_lightning_alias_uses_verified_free_endpoint_and_shared_pacing():
    from megazword.free_apis import free_backends
    backend = {b.name: b for b in free_backends(config.DEFAULT_FREE)}["nvidia-lightning"]
    assert backend.model == "nvidia/nemotron-3.5-lightning-30b-a3b"
    assert backend.key_env == "NVIDIA_API_KEY"
    assert "nvidia-lightning" in config.DEFAULT_FREE_FAILOVER
    assert all("nvidia-lightning" in route for route in config.DEFAULT_ROUTE.values())


def test_nvidia_model_aliases_share_provider_pacing_file(tmp_path, monkeypatch):
    from megazword import agent
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(agent.time, "sleep", lambda _: None)
    deadline = agent.time.monotonic() + 5
    pace = {"nvidia": 0.001}
    agent.pace_call("nvidia", pace, deadline)
    agent.pace_call("nvidia-lightning", pace, deadline)
    assert (tmp_path / "agent-pace" / "nvidia.json").exists()
    assert not (tmp_path / "agent-pace" / "nvidia-lightning.json").exists()


def test_successful_response_records_provider_request_quota(api, monkeypatch):
    class Response(io.BytesIO):
        headers = {"x-ratelimit-remaining-requests": "42",
                   "x-ratelimit-limit-requests": "1000",
                   "x-ratelimit-reset-requests": "30m"}
        def __enter__(self): return self
        def __exit__(self, *args): self.close()
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: Response(
        json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()))
    assert api.run("hello").ok
    assert (api.remaining_requests, api.limit_requests) == (42, 1000)


def test_low_request_quota_is_persisted_until_header_reset(api, monkeypatch, tmp_path):
    from megazword import free_apis
    monkeypatch.setattr(config, "HOME", tmp_path)
    free_apis._record_request_quota("test", 49, 1000, "30m")
    assert free_apis.request_quota_low("test")
    assert not free_apis.request_quota_low("another-model")
    free_apis._record_request_quota("test", 900, 1000, "1h")
    assert not free_apis.request_quota_low("test")


def test_all_default_routes_try_free_backends_before_paid_plans():
    free = {"openrouter", "groq", "cloudflare", "zai", "gemini-api", "gemini",
            "mistral", "nvidia", "tencent", "ollama",
            "tencent-glm-5.3-flash", "tencent-glm-5.3",
            "tencent-kimi-k2.7-code", "tencent-kimi-k3",
            "tencent-deepseek-v4-pro", "tencent-deepseek-v4-flash-vision-exp"}
    paid = {"claude", "codex", "grok"}
    for route in config.DEFAULT_ROUTE.values():
        free_positions = [i for i, name in enumerate(route) if name in free]
        paid_positions = [i for i, name in enumerate(route) if name in paid]
        assert free_positions and paid_positions
        assert max(free_positions) < min(paid_positions)
    assert config.DEFAULT_FREE_FAILOVER[:6] == [
        "tencent-glm-5.3-flash", "tencent-glm-5.3",
        "tencent-kimi-k2.7-code", "tencent-kimi-k3",
        "tencent-deepseek-v4-pro", "tencent-deepseek-v4-flash-vision-exp",
    ]
    assert not ({"kimi", "qwen-coder", "deepseek"} & set(config.DEFAULT_FREE_FAILOVER))


def test_gemini_cli_and_developer_api_are_distinct_backends():
    from megazword.backends import GeminiBackend, default_backends
    from megazword.free_apis import OpenAICompatibleBackend
    backends = default_backends()
    assert isinstance(backends["gemini"], GeminiBackend)
    assert isinstance(backends["gemini-api"], OpenAICompatibleBackend)
    assert backends["gemini"].name != backends["gemini-api"].name
    assert all("gemini-api" in route and "gemini" in route
               for route in config.DEFAULT_ROUTE.values())


def test_openrouter_fallback_is_free_even_without_config_override():
    from megazword.free_apis import free_backends
    openrouter = next(b for b in free_backends({}) if b.name == "openrouter")
    assert openrouter.model == "openrouter/free"
    assert openrouter.trains_on_data


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


def test_cerebras_free_model_defaults_and_override(monkeypatch):
    from megazword.free_apis import OpenAICompatibleBackend, free_backends
    models = dict(config.DEFAULT_FREE)
    backends = {b.name: b for b in free_backends(models)}
    cerebras = backends["cerebras"]
    assert isinstance(cerebras, OpenAICompatibleBackend)
    assert cerebras.base_url == "https://api.cerebras.ai/v1"
    assert cerebras.model == "qwen-3.8-27b"
    assert cerebras.key_env == "CEREBRAS_API_KEY"
    models["cerebras"] = "gpt-oss-120b"
    assert {b.name: b for b in free_backends(models)}["cerebras"].model == "gpt-oss-120b"


def test_tencent_tokenhub_request_uses_deepseek_v4_pro_singapore_and_key(monkeypatch):
    from megazword.free_apis import free_backends
    monkeypatch.setenv("TENCENT_TOKENHUB_API_KEY", "secret-test-credential")
    backend = {b.name: b for b in free_backends(config.DEFAULT_FREE)}["tencent"]
    seen = []

    def fake(request, timeout):
        seen.append(request)
        return reply("ok")

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    result = backend.run("Reply with ok")
    assert result.ok and result.text == "ok"
    assert seen[0].full_url == (
        "https://tokenhub-intl.tencentcloudmaas.com/v1/chat/completions")
    assert seen[0].get_header("Authorization") == "Bearer secret-test-credential"
    assert json.loads(seen[0].data)["model"] == "deepseek-v4-pro"


def test_all_six_live_verified_tencent_models_are_routed():
    backends = default_backends()
    assert "tencent" in backends
    assert all("tencent" not in route for route in config.DEFAULT_ROUTE.values())
    assert "tencent" not in config.DEFAULT_FREE_FAILOVER
    working = ("tencent-glm-5.3-flash", "tencent-glm-5.3",
               "tencent-kimi-k2.7-code", "tencent-kimi-k3",
               "tencent-deepseek-v4-pro",
               "tencent-deepseek-v4-flash-vision-exp")
    assert set(working).issubset(backends)
    assert all(route[:6] == list(working) for route in config.DEFAULT_ROUTE.values())
    assert all(name in config.DEFAULT_FREE_FAILOVER for name in working)
    assert all(backends[name].key_env == "TENCENT_TOKENHUB_API_KEY"
               for name in working)
    assert all(backends[name].base_url == backends["tencent"].base_url
               for name in working)
    assert {name: backends[name].model for name in working} == {
        "tencent-glm-5.3-flash": "glm-5.3-flash",
        "tencent-glm-5.3": "glm-5.3",
        "tencent-kimi-k2.7-code": "kimi-k2.7-code",
        "tencent-kimi-k3": "kimi-k3",
        "tencent-deepseek-v4-pro": "deepseek-v4-pro",
        "tencent-deepseek-v4-flash-vision-exp": "deepseek/deepseek-v4-flash-vision-exp",
    }


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


def test_gemini_api_default_model_is_flash_lite():
    assert config.DEFAULT_FREE["gemini-api"] == "gemini-3.5-flash-lite"
    assert default_backends()["gemini-api"].model == "gemini-3.5-flash-lite"


def test_openrouter_default_uses_free_router():
    assert config.DEFAULT_FREE["openrouter"] == "openrouter/free"
    assert default_backends()["openrouter"].model == "openrouter/free"


def test_ovh_is_keyless_and_never_sends_a_key(monkeypatch):
    from megazword.free_apis import KEYLESS, free_backends
    monkeypatch.setenv("OVH_AI_ENDPOINTS_ACCESS_TOKEN", "secret-test-credential")
    backend = {b.name: b for b in free_backends(config.DEFAULT_FREE)}["ovh"]
    assert "ovh" in KEYLESS and backend.available() and backend.trains_on_data
    seen = []

    def fake(request, timeout):
        seen.append(request)
        return reply("ok")

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert backend.run("Reply with ok").text == "ok"
    assert seen[0].full_url == "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions"
    assert seen[0].get_header("Authorization") is None
    assert json.loads(seen[0].data)["model"] == "Qwen3.5-397B-A17B"
    assert all("ovh" in names for names in config.DEFAULT_ROUTE.values())
    assert "ovh" in config.DEFAULT_FREE_FAILOVER


def test_keyed_backend_without_key_still_refuses(monkeypatch):
    monkeypatch.delenv("MISSING_TEST_KEY", raising=False)
    backend = OpenAICompatibleBackend("t", base_url="https://example.test/v1", model="m",
                                      key_env="MISSING_TEST_KEY")
    monkeypatch.setattr("megazword.free_apis.get_key", lambda name: None)
    assert not backend.available()
    with pytest.raises(RuntimeError, match="API key not set"):
        backend.chat([{"role": "user", "content": "hi"}])


def test_each_ovh_model_is_its_own_keyless_pool():
    from megazword import agent
    from megazword.free_apis import KEYLESS, free_backends
    backends = {b.name: b for b in free_backends(config.DEFAULT_FREE)}
    models = {n: backends[n].model for n in KEYLESS}
    assert models == {"ovh": "Qwen3.5-397B-A17B", "ovh-120b": "gpt-oss-120b", "ovh-qwen": "Qwen3.8-27B"}
    assert all(backends[n].keyless and backends[n].available() for n in KEYLESS)
    assert all(agent.DEFAULT_PACE[n] == 31 for n in KEYLESS)  # 2 requests/min per model
