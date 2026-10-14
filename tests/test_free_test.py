"""Free backend checks use fake HTTP only; no real prompts or credentials."""

import io
import json
import urllib.error
import urllib.request

import pytest

from megazword import cli, config
from megazword.free_apis import FREE_KEYS


def response(content="ok", local=False):
    payload = ({"response": content} if local else
               {"choices": [{"message": {"content": content}}]})
    return io.BytesIO(json.dumps(payload).encode())


def test_all_keyed_backends_once_and_configured_models(monkeypatch, capsys):
    for _, key in FREE_KEYS:
        monkeypatch.setenv(key, "fake-test-key")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "fake-account")
    names = [name for name, _ in FREE_KEYS] + ["ollama"]
    cfg = config.Config(free={name: "test-" + name for name in names})
    seen = []

    def fake(request, timeout):
        body = json.loads(request.data)
        name = body["model"].removeprefix("test-")
        assert timeout == 30
        if name == "ollama":
            assert request.full_url.endswith("/api/generate")
            assert body["prompt"] == "Reply with: ok"
        else:
            assert body["messages"] == [{"role": "user", "content": "Reply with: ok"}]
        seen.append(name)
        return response(local=name == "ollama")

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert cli.main(["free", "test"], cfg=cfg) == 0
    assert seen == names
    output = capsys.readouterr().out.splitlines()
    assert output[0].split() == ["name", "status", "seconds", "error"]
    assert len(output) == len(names) + 1
    for row, name in zip(output[1:], names):
        columns = row.split()
        assert columns[:2] == [name, "ok"]
        assert float(columns[2]) >= 0


def test_missing_keys_skip_apis_but_test_keyless_ollama(monkeypatch, capsys):
    seen = []

    def fake(request, timeout):
        seen.append(request.full_url)
        return response(local=True)

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert cli.main(["free", "test"], cfg=config.Config()) == 0
    assert len(seen) == 1 and seen[0].endswith("/api/generate")
    assert len(capsys.readouterr().out.splitlines()) == 2


@pytest.mark.parametrize("failure", ["http", "timeout", "empty", "network"])
def test_failure_does_not_stop_later_backends(monkeypatch, capsys, failure):
    monkeypatch.setenv("GROQ_API_KEY", "fake-test-key")
    monkeypatch.setenv("MISTRAL_API_KEY", "fake-test-key")
    seen = []

    def fake(request, timeout):
        seen.append(request.full_url)
        if "groq" in request.full_url:
            if failure == "http":
                raise urllib.error.HTTPError(request.full_url, 429, "fake-test-key", {},
                                             io.BytesIO(b"fake-test-key"))
            if failure == "timeout":
                raise TimeoutError("fake-test-key")
            if failure == "network":
                raise urllib.error.URLError("fake-test-key")
            return response("")
        return response(local=request.full_url.endswith("/api/generate"))

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert cli.main(["free", "test"], cfg=config.Config()) == 1
    output = capsys.readouterr().out
    assert len(seen) == 3
    rows = [row.split() for row in output.splitlines()[1:]]
    assert [(row[0], row[1]) for row in rows] == [
        ("groq", "failed"), ("mistral", "ok"), ("ollama", "ok")]
    assert len(rows[0]) > 3
    assert "fake-test-key" not in output


def test_missing_cloudflare_account_is_reported_without_http(monkeypatch, capsys):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "fake-token")
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: response(local=True))
    assert cli.main(["free", "test"], cfg=config.Config()) == 1
    assert "API key not set" in capsys.readouterr().out


def test_local_errors_scrub_secrets_urls_and_newlines(monkeypatch, capsys):
    monkeypatch.setenv("OTHER_SECRET", "fake-sensitive-value")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "fake-account")

    def fake(*args, **kwargs):
        raise RuntimeError("offline\nfake-sensitive-value fake-account "
                           "https://private.test/?auth=hidden Bearer opaque " + "x" * 200)

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert cli.main(["free", "test"], cfg=config.Config()) == 1
    output = capsys.readouterr().out
    for private in ("fake-sensitive-value", "fake-account", "private.test", "hidden", "opaque"):
        assert private not in output
    assert len(output.splitlines()) == 2
    assert "offline" in output and "[REDACTED]" in output
    assert len(output.splitlines()[1].split(maxsplit=3)[3]) <= 120


def test_help_lists_free_command(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    assert "free" in capsys.readouterr().out
