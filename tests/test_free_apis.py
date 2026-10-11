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
                            io.BytesIO(b"secret-test-credential")), "API HTTP error 429"),
    (TimeoutError("secret-test-credential"), "API request timed out"),
    (urllib.error.URLError(TimeoutError("secret-test-credential")), "API request timed out"),
    (urllib.error.URLError("secret-test-credential"), "API connection failed"),
    (OSError("secret-test-credential"), "API request failed"),
])
def test_failures_are_safe_results(api, monkeypatch, error, message):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(urllib.request, "urlopen", fail)
    result = api.run("hi")
    assert not result.ok and result.text == "" and result.error == message
    assert "secret-test-credential" not in repr(result)


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
    assert not {"openrouter", "groq"} & default_backends(edit=True).keys()


@pytest.mark.parametrize("name, key_env", [("openrouter", "OPENROUTER_API_KEY"),
                                           ("groq", "GROQ_API_KEY")])
def test_cli_forced_and_edit_exclusion(name, key_env, monkeypatch, capsys):
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
    assert cli.main(["run", "hello", "-m", name, "--edit"], cfg=cfg) == 2
    assert len(calls) == 1
    assert cli.main(["backends"], cfg=cfg) == 0
    output = capsys.readouterr().out
    assert "openrouter" in output and "groq" in output
    assert "secret-test-credential" not in output


@pytest.mark.parametrize("model", ['""', '123'])
def test_bad_model_config(tmp_path, model):
    path = tmp_path / "config.toml"
    path.write_text(f"[free.groq]\nmodel = {model}\n")
    with pytest.raises(ValueError, match="nonempty string"):
        config.load(path)
