import io
import json
import urllib.error

import pytest

from megazword import ollama


def test_ollama_generate_success(monkeypatch):
    seen = []

    def mock_urlopen(req, timeout=60):
        seen.append((req.full_url, json.loads(req.data.decode()), timeout))
        resp_data = {"response": "Hello from ollama!"}
        return io.BytesIO(json.dumps(resp_data).encode())

    monkeypatch.setattr(ollama.urllib.request, "urlopen", mock_urlopen)

    result = ollama.generate("Say hello", "llama3", timeout=10)
    assert result == "Hello from ollama!"
    assert len(seen) == 1
    url, body, timeout = seen[0]
    assert url == "http://127.0.0.1:11434/api/generate"
    assert body["model"] == "llama3"
    assert body["prompt"] == "Say hello"
    assert timeout == 10


def test_ollama_generate_chat_success(monkeypatch):
    seen = []

    def mock_urlopen(req, timeout=60):
        seen.append((req.full_url, json.loads(req.data.decode()), timeout))
        resp_data = {"message": {"content": "Hello chat user!"}}
        return io.BytesIO(json.dumps(resp_data).encode())

    monkeypatch.setattr(ollama.urllib.request, "urlopen", mock_urlopen)

    messages = [{"role": "user", "content": "Hi"}]
    result = ollama.generate("", "llama3", messages=messages, json_format=True)
    assert result == "Hello chat user!"
    assert len(seen) == 1
    url, body, _ = seen[0]
    assert url == "http://127.0.0.1:11434/api/chat"
    assert body["messages"] == messages
    assert body["format"] == "json"
    assert "prompt" not in body


def test_ollama_generate_model_missing_404(monkeypatch):
    def mock_urlopen(req, timeout=60):
        raise urllib.error.HTTPError(
            url=req.full_url,
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=io.BytesIO(b'{"error": "model \'missing-model\' not found"}')
        )

    monkeypatch.setattr(ollama.urllib.request, "urlopen", mock_urlopen)

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        ollama.generate("hello", "missing-model")
    assert exc_info.value.code == 404
    assert "model" in exc_info.value.read().decode()


def test_ollama_generate_connection_refused(monkeypatch):
    def mock_urlopen(req, timeout=60):
        raise URLErrorReason("Connection refused")

    # urllib.error.URLError takes reason or error object
    class URLErrorReason(urllib.error.URLError):
        def __init__(self, reason):
            super().__init__(reason)

    monkeypatch.setattr(ollama.urllib.request, "urlopen", mock_urlopen)

    with pytest.raises(urllib.error.URLError) as exc_info:
        ollama.generate("hello", "llama3")
    assert "Connection refused" in str(exc_info.value)


def test_ollama_reachable_and_models(monkeypatch):
    # Test reachable true
    def mock_urlopen_version(req, timeout=2):
        return io.BytesIO(b'{"version": "0.1.0"}')

    monkeypatch.setattr(ollama.urllib.request, "urlopen", mock_urlopen_version)
    assert ollama.reachable("http://localhost:11434") is True

    # Test reachable false (connection error)
    def mock_urlopen_error(req, timeout=2):
        raise OSError("Connection refused")

    monkeypatch.setattr(ollama.urllib.request, "urlopen", mock_urlopen_error)
    assert ollama.reachable("http://localhost:11434") is False

    # Test installed_models / models
    def mock_urlopen_tags(req, timeout=2):
        return io.BytesIO(json.dumps({"models": [{"name": "llama3:latest"}, {"name": "mistral"}]}).encode())

    monkeypatch.setattr(ollama.urllib.request, "urlopen", mock_urlopen_tags)
    assert ollama.installed_models() == ["llama3:latest", "mistral"]
    assert ollama.models() == {"llama3:latest", "mistral"}
