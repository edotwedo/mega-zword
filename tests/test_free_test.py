import pytest

from megazword import cli, config, free_test
from megazword.backends import Backend, Result


class FakeBackend(Backend):
    def __init__(self, name, available=True, result=None):
        super().__init__(name)
        self.is_available = available
        self.result = result or Result(name, "ok", True, 0.25)
        self.prompts = []

    def available(self):
        return self.is_available

    def run(self, prompt):
        self.prompts.append(prompt)
        return self.result


def test_free_test_checks_available_providers_once_and_omits_unconfigured(
        monkeypatch, capsys):
    monkeypatch.setattr(free_test, "OllamaBackend",
                        lambda name, model: FakeBackend(name, available=False))
    groq = FakeBackend("groq")
    gemini = FakeBackend("gemini-api")
    missing = FakeBackend("nvidia", available=False)

    status = free_test.command(
        {"groq": groq, "gemini-api": gemini, "nvidia": missing}, {})

    out = capsys.readouterr().out
    assert status == 0
    assert groq.prompts == ["Reply with: ok"]
    assert gemini.prompts == ["Reply with: ok"]
    assert missing.prompts == []
    assert "groq" in out and "gemini-api" in out and "nvidia" not in out
    assert "ok" in out and "0.2" in out
    assert groq.timeout == free_test.TIMEOUT_SECONDS


def test_free_test_includes_all_six_tencent_models():
    names = {
        "tencent-glm-5.3-flash", "tencent-glm-5.3",
        "tencent-kimi-k2.7-code", "tencent-kimi-k3",
        "tencent-deepseek-v4-pro", "tencent-deepseek-v4-flash-vision-exp",
    }
    assert names.issubset(free_test.PROVIDERS)
    assert "tencent" not in free_test.PROVIDERS


def test_free_test_allows_slow_tencent_replies(monkeypatch):
    monkeypatch.setattr(free_test, "OllamaBackend",
                        lambda name, model: FakeBackend(name, available=False))
    backend = FakeBackend("tencent-kimi-k3")
    assert free_test.command({backend.name: backend}, {}, [backend.name]) == 0
    assert backend.timeout == 180


def test_free_test_reports_failures_and_redacts_credentials(monkeypatch, capsys):
    monkeypatch.setenv("TEST_API_KEY", "secret-provider-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "secret-account-id")
    monkeypatch.setattr(free_test, "OllamaBackend",
                        lambda name, model: FakeBackend(name, available=False))
    broken = FakeBackend(
        "groq", result=Result("groq", "", False, 1.5,
                              "denied secret-provider-token from https://secret-account-id.test/"))

    status = free_test.command({"groq": broken}, {})

    out = capsys.readouterr().out
    assert status == 1
    assert "groq" in out and "failed" in out and "1.5" in out
    assert "denied" in out
    assert "secret-provider-token" not in out
    assert "secret-account-id" not in out
    assert "https://" not in out


def test_free_test_reports_empty_configuration(monkeypatch, capsys):
    monkeypatch.setattr(free_test, "OllamaBackend",
                        lambda name, model: FakeBackend(name, available=False))
    assert free_test.command({}, {}) == 0
    assert "No configured free providers found." in capsys.readouterr().out


def test_free_test_checks_reachable_ollama(monkeypatch, capsys):
    local = FakeBackend("ollama")
    monkeypatch.setattr(free_test, "OllamaBackend",
                        lambda name, model: local if model == "local-coder" else None)

    assert free_test.command({}, {"ollama": "local-coder"}) == 0

    assert local.prompts == ["Reply with: ok"]
    assert "ollama" in capsys.readouterr().out


def test_selected_providers_are_the_only_ones_called(monkeypatch, capsys):
    monkeypatch.setattr(free_test, "OllamaBackend",
                        lambda name, model: FakeBackend(name, available=False))
    groq = FakeBackend("groq")
    api = FakeBackend("gemini-api")

    assert free_test.command({"groq": groq, "gemini-api": api}, {},
                             ["gemini-api", "gemini-api"]) == 0

    assert api.prompts == ["Reply with: ok"]
    assert not groq.prompts
    assert "gemini-api" in capsys.readouterr().out


def test_selected_unavailable_provider_returns_failure(monkeypatch, capsys):
    monkeypatch.setattr(free_test, "OllamaBackend",
                        lambda name, model: FakeBackend(name, available=False))
    api = FakeBackend("gemini-api", available=False)

    assert free_test.command({"gemini-api": api}, {},
                             ["gemini-api"]) == 1

    output = capsys.readouterr().out
    assert "gemini-api" in output and "not configured or unavailable" in output
    assert not api.prompts


def test_selected_out_provider_is_skipped_without_failure(monkeypatch, capsys):
    monkeypatch.setattr(free_test, "OllamaBackend",
                        lambda name, model: FakeBackend(name, available=False))
    cli_backend = FakeBackend("gemini")

    assert free_test.command({"gemini": cli_backend}, {}, ["gemini"],
                             {"gemini"}) == 0

    output = capsys.readouterr().out
    assert "gemini" in output and "marked out; skipped" in output
    assert not cli_backend.prompts


def test_free_test_skips_stale_openrouter_alias_before_inference(monkeypatch, capsys):
    from megazword.free_apis import OpenAICompatibleBackend
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    backend = OpenAICompatibleBackend("qwen-coder", base_url="https://openrouter.ai/api/v1",
                                      model="qwen/qwen3-coder:free",
                                      key_env="OPENROUTER_API_KEY")
    monkeypatch.setattr(free_test.openrouter_catalog, "fetch_catalog",
                        lambda: {"data": [model_record("other/model:free")]})
    monkeypatch.setattr(backend, "run", lambda prompt: pytest.fail("stale ID must not be called"))

    assert free_test.command({"qwen-coder": backend}, {}, ["qwen-coder"]) == 1
    output = capsys.readouterr().out
    assert "not verified as free and tool-capable" in output


def model_record(model_id):
    return {"id": model_id, "name": model_id, "pricing": {"prompt": "0", "completion": "0"},
            "supported_parameters": ["tools"], "context_length": 1024}


def test_free_test_calls_openrouter_model_listed_as_free(monkeypatch, capsys):
    from megazword.backends import Result
    from megazword.free_apis import OpenAICompatibleBackend
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    backend = OpenAICompatibleBackend("openrouter", base_url="https://openrouter.ai/api/v1",
                                      model="openrouter/free", key_env="OPENROUTER_API_KEY")
    monkeypatch.setattr(free_test.openrouter_catalog, "fetch_catalog",
                        lambda: {"data": [model_record("openrouter/free")]})
    calls = []
    monkeypatch.setattr(backend, "run", lambda prompt: calls.append(prompt) or
                        Result("openrouter", "ok", True, 0.1))

    assert free_test.command({"openrouter": backend}, {}, ["openrouter"]) == 0
    assert calls == ["Reply with: ok"]
    assert "openrouter" in capsys.readouterr().out


def test_free_test_cli_command_is_wired(monkeypatch, capsys):
    monkeypatch.setattr(free_test, "OllamaBackend",
                        lambda name, model: FakeBackend(name, available=False))
    result = cli.main(["free", "test"], {"groq": FakeBackend("groq")},
                      config.Config())
    assert result == 0
    assert "groq" in capsys.readouterr().out


def test_free_test_cli_accepts_repeated_provider_selection(monkeypatch, capsys):
    monkeypatch.setattr(free_test, "OllamaBackend",
                        lambda name, model: FakeBackend(name, available=False))
    api = FakeBackend("gemini-api")
    groq = FakeBackend("groq")
    result = cli.main(["free", "test", "--provider", "gemini-api",
                       "--provider", "gemini-api"],
                      {"gemini-api": api, "groq": groq}, config.Config())
    assert result == 0
    assert api.prompts == ["Reply with: ok"]
    assert not groq.prompts


def test_free_test_cli_rejects_unknown_provider_before_network(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["free", "test", "--provider", "unknown-provider"],
                 {"groq": FakeBackend("groq")}, config.Config())
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
