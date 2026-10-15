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


def test_free_test_cli_command_is_wired(monkeypatch, capsys):
    monkeypatch.setattr(free_test, "OllamaBackend",
                        lambda name, model: FakeBackend(name, available=False))
    result = cli.main(["free", "test"], {"groq": FakeBackend("groq")},
                      config.Config())
    assert result == 0
    assert "groq" in capsys.readouterr().out
