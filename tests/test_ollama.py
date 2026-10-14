import io
import json
import urllib.error
from unittest.mock import Mock

import pytest

from megazword import ollama


URL = "http://ollama.test:11434"


@pytest.fixture
def http(monkeypatch):
    """Replace every HTTP call, including any unexpected extra requests."""
    fake = Mock(side_effect=AssertionError("unexpected HTTP call"))
    monkeypatch.setattr(ollama.urllib.request, "urlopen", fake)
    return fake


@pytest.mark.parametrize("json_format", [False, True])
def test_generate_success(http, json_format):
    response = io.BytesIO(json.dumps({"response": "  hello world  "}).encode())
    http.side_effect = None
    http.return_value = response

    assert ollama.generate("hello", "test-model", URL,
                           json_format=json_format, timeout=7) == "  hello world  "

    http.assert_called_once()
    request = http.call_args.args[0]
    assert http.call_args.kwargs == {"timeout": 7}
    assert request.full_url == f"{URL}/api/generate"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    expected = {"model": "test-model", "prompt": "hello", "stream": False,
                "keep_alive": "30m"}
    if json_format:
        expected["format"] = "json"
    assert json.loads(request.data) == expected
    assert response.closed


def test_generate_missing_model(http):
    error = urllib.error.HTTPError(
        f"{URL}/api/generate", 404, "Not Found", {},
        io.BytesIO(b'{"error":"model test-model not found"}'),
    )
    http.side_effect = error

    with pytest.raises(urllib.error.HTTPError) as caught:
        ollama.generate("hello", "test-model", URL)

    assert caught.value is error
    assert caught.value.code == 404
    http.assert_called_once()


@pytest.mark.parametrize("call", [ollama.generate, ollama.installed_models, ollama.models])
def test_connection_refused_propagates(http, call):
    error = urllib.error.URLError(ConnectionRefusedError("connection refused"))
    http.side_effect = error

    with pytest.raises(urllib.error.URLError) as caught:
        if call is ollama.generate:
            call("hello", "test-model", URL)
        else:
            call(URL)

    assert caught.value is error
    assert isinstance(caught.value.reason, ConnectionRefusedError)
    http.assert_called_once()


def test_reachable_success(http):
    response = io.BytesIO(b'{"version":"test"}')
    http.side_effect = None
    http.return_value = response

    assert ollama.reachable(URL, timeout=3) is True
    http.assert_called_once_with(f"{URL}/api/version", timeout=3)
    assert response.closed


def test_reachable_connection_refused(http):
    http.side_effect = urllib.error.URLError(ConnectionRefusedError("connection refused"))

    assert ollama.reachable(URL, timeout=3) is False
    http.assert_called_once_with(f"{URL}/api/version", timeout=3)


@pytest.mark.parametrize("call, expected", [
    (ollama.installed_models, ["second:latest", "first:latest", "second:latest"]),
    (ollama.models, {"first:latest", "second:latest"}),
])
def test_models_success(http, call, expected):
    response = io.BytesIO(json.dumps({"models": [
        {"name": "second:latest"}, {"name": "first:latest"}, {"name": "second:latest"},
    ]}).encode())
    http.side_effect = None
    http.return_value = response

    assert call(URL, timeout=4) == expected
    http.assert_called_once_with(f"{URL}/api/tags", timeout=4)
    assert response.closed
