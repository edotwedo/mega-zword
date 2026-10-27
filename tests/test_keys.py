import io
import json
import sys
import urllib.error

import pytest

from megazword import cli, config, credential_store as vault, keys
from megazword.free_apis import OpenAICompatibleBackend


@pytest.fixture
def store(monkeypatch):
    values = {}
    monkeypatch.setattr(vault, "available", lambda: True)
    monkeypatch.setattr(vault, "read", values.get)
    monkeypatch.setattr(vault, "write", values.__setitem__)
    monkeypatch.setattr(config, "_windows_user_env", lambda name: None)
    return values


def test_lookup_precedence_and_unavailable(store, monkeypatch):
    store["GROQ_API_KEY"] = "vault-fake"
    assert keys.get_key("GROQ_API_KEY") == "vault-fake"
    monkeypatch.setenv("GROQ_API_KEY", "env-fake")
    assert keys.get_key("GROQ_API_KEY") == "env-fake"
    monkeypatch.delenv("GROQ_API_KEY")
    monkeypatch.setattr(vault, "read", lambda name: (_ for _ in ()).throw(vault.VaultError("unavailable")))
    assert keys.get_key("GROQ_API_KEY") is None


def test_vault_backend_and_all_output_scrubbing(store, monkeypatch):
    from megazword import guard, export, free_apis, free_test, run_control, job_workers
    store.update(GROQ_API_KEY="unusual-vault-value", CLOUDFLARE_ACCOUNT_ID="a" * 32)
    backend = OpenAICompatibleBackend("test", base_url="https://example.test/{account}",
                                      key_env="GROQ_API_KEY", extra_env=("CLOUDFLARE_ACCOUNT_ID",))
    assert backend.available()
    def response(request, timeout):
        assert request.get_header("Authorization") == "Bearer unusual-vault-value"
        assert "a" * 32 in request.full_url
        assert "unusual-vault-value" not in request.data.decode()
        return io.BytesIO(json.dumps({"choices": [{"message": {"content": "unusual-vault-value"}}]}).encode())
    monkeypatch.setattr(free_apis.urllib.request, "urlopen", response)
    assert backend.chat([{"role": "user", "content": "unusual-vault-value"}])["content"] == "[REDACTED]"
    monkeypatch.setenv("GROQ_API_KEY", "env-fake")
    for scrubber in (guard.scrub, export.redact, free_test._safe_reason, run_control.safe, job_workers._safe):
        result = scrubber("unusual-vault-value env-fake")
        assert "unusual-vault-value" not in result and "env-fake" not in result
    reason = free_apis._safe_reason(io.BytesIO(b'{"error":{"message":"unusual-vault-value"}}'))
    assert "unusual-vault-value" not in reason


def test_show_deduplicates_providers_and_never_prints_values(store, monkeypatch, capsys):
    for name in keys.key_names():
        store[name] = "fake-private-value"
    calls = []
    monkeypatch.setattr(keys, "_probe", lambda backend: calls.append(backend.key_env) or "ok")
    assert cli.main(["keys"]) == 0
    output = capsys.readouterr().out
    assert "fake-private-value" not in output
    assert len(calls) == len(set(calls)) == len(keys.key_names()) - 2
    assert "room token; not probed" in output
    for name in keys.key_names():
        assert output.count(name) == 1


def test_move_user_registry_verify_and_no_automatic_delete(store, monkeypatch, capsys):
    monkeypatch.setattr(keys, "_ON_WINDOWS", True)
    saved = {"GROQ_API_KEY": "fake-registry-value"}
    monkeypatch.setattr(config, "_windows_user_env", saved.get)
    assert cli.main(["keys", "move"]) == 0
    assert store == saved
    assert saved["GROQ_API_KEY"] == "fake-registry-value"
    output = capsys.readouterr().out
    assert "fake-registry-value" not in output
    assert "[Environment]::SetEnvironmentVariable('GROQ_API_KEY', $null, 'User')" in output


def test_move_conflict_and_failed_verification_emit_no_clear_command(store, monkeypatch, capsys):
    monkeypatch.setenv("GROQ_API_KEY", "fake-process")
    monkeypatch.setattr(config, "_windows_user_env", lambda n: "fake-registry" if n == "GROQ_API_KEY" else None)
    assert keys.move() == 1
    assert not store
    monkeypatch.setattr(config, "_windows_user_env", lambda n: None)
    monkeypatch.setattr(vault, "read", lambda n: "incorrect-fake")
    assert keys.move() == 1
    output = capsys.readouterr().out
    assert "SetEnvironmentVariable" not in output
    assert "fake-process" not in output and "fake-registry" not in output
    assert keys.os.environ["GROQ_API_KEY"] == "fake-process"


def test_move_refused_when_store_unavailable(monkeypatch, capsys):
    monkeypatch.setattr(vault, "available", lambda: False)
    assert keys.move() == 1
    assert "unavailable" in capsys.readouterr().out
    with pytest.raises(vault.VaultError):
        vault.write("GROQ_API_KEY", "fake")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX secret file")
def test_posix_move_copies_env_into_secret_file(monkeypatch, capsys):
    monkeypatch.setattr(keys, "_ON_WINDOWS", False)
    for name in keys.key_names():
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "fake-env-value")
    assert keys.move() == 0
    assert vault.read("GROQ_API_KEY") == "fake-env-value"
    assert keys.get_key("GROQ_API_KEY") == "fake-env-value"
    output = capsys.readouterr().out
    assert "fake-env-value" not in output
    assert "SetEnvironmentVariable" not in output and "shell profile" in output


@pytest.mark.parametrize("code, expected", [(401, "rejected (401)"), (403, "rejected (403)"),
    (429, "rate limited"), (500, "no answer"), (302, "no answer")])
def test_probe_errors_do_not_expose_provider_details(store, monkeypatch, code, expected):
    store["GROQ_API_KEY"] = "fake-private"
    class Opener:
        def open(self, request, timeout):
            raise urllib.error.HTTPError("https://fake-private", code, "fake-private", {}, io.BytesIO(b"fake-private"))
    monkeypatch.setattr(keys.urllib.request, "build_opener", lambda *a: Opener())
    assert keys._probe(OpenAICompatibleBackend("groq", key_env="GROQ_API_KEY", base_url="https://example.test")) == expected


@pytest.mark.parametrize("name, endpoint, header", [
    ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1/key", "Authorization"),
    ("GOOGLE_AI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1", "X-goog-api-key"),
    ("CLOUDFLARE_API_TOKEN", "https://api.cloudflare.com/client/v4/accounts/" + "a" * 32 + "/ai/models/search?per_page=1", "Authorization"),
])
def test_metadata_only_single_request(store, monkeypatch, name, endpoint, header):
    store.update({name: "fake-private", "CLOUDFLARE_ACCOUNT_ID": "a" * 32})
    calls = []
    class Response(io.BytesIO):
        status = 200
    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            assert request.full_url == endpoint
            assert request.get_method() == "GET" and request.data is None
            assert "fake-private" in request.get_header(header)
            assert timeout == 10
            return Response(b'{"data":[]}')
    monkeypatch.setattr(keys.urllib.request, "build_opener", lambda *a: Opener())
    assert keys._probe(OpenAICompatibleBackend("fake", key_env=name)) == "ok"
    assert len(calls) == 1


def test_missing_keys_never_call_network(monkeypatch, capsys):
    monkeypatch.setattr(keys, "_probe", lambda b: pytest.fail("missing key called provider"))
    assert keys.show() == 0
    assert "missing" in capsys.readouterr().out


def test_redirects_are_never_followed():
    assert keys._NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.test") is None


def test_all_backend_prompts_and_errors_scrub_vault_values(store):
    from megazword.backends import Backend
    store["GROQ_API_KEY"] = "fake-private-value"
    class Fake(Backend):
        def _run(self, prompt):
            assert "fake-private-value" not in prompt
            raise RuntimeError("fake-private-value")
    result = Fake("fake", trains_on_data=False).run("fake-private-value")
    assert not result.ok and "fake-private-value" not in result.error


def test_payload_redaction_reads_the_vault_once_and_scrubs_every_string(monkeypatch):
    reads = []

    def read(name):
        reads.append(name)
        return "vault-secret-value" if name == "GROQ_API_KEY" else None
    monkeypatch.setattr(vault, "read", read)
    payload = [{"role": "user", "content": f"line {i} vault-secret-value"} for i in range(20)]
    out = keys.redact_payload(payload)
    assert all("vault-secret-value" not in m["content"] and "[REDACTED]" in m["content"] for m in out)
    assert len(reads) == len(keys.key_names())  # one pass over the vault, not one per string
