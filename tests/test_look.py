"""Exercise the vision helper without contacting Gemini."""

import importlib.util
import io
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "look.py"
spec = importlib.util.spec_from_file_location("look", SCRIPT)
look = importlib.util.module_from_spec(spec)
spec.loader.exec_module(look)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def unexpected_request(*args, **kwargs):
        pytest.fail("unexpected network request")

    monkeypatch.setattr(look.urllib.request, "urlopen", unexpected_request)
    monkeypatch.setenv("GOOGLE_AI_API_KEY", "test-key")
    monkeypatch.setenv("LOOK_MODEL", "test-model")


@pytest.fixture
def image_path(tmp_path):
    path = tmp_path / "image.png"
    path.write_bytes(b"test image bytes")
    return path


def test_missing_api_key_returns_one_without_network(monkeypatch, image_path, capsys):
    monkeypatch.delenv("GOOGLE_AI_API_KEY", raising=False)

    assert look.main(["look.py", str(image_path)]) == 1

    output = capsys.readouterr()
    assert output.out == ""
    assert "GOOGLE_AI_API_KEY is not set" in output.err


def test_unreadable_path_returns_one(tmp_path, capsys):
    assert look.main(["look.py", str(tmp_path / "missing.png")]) == 1

    output = capsys.readouterr()
    assert output.out == ""
    assert "cannot read" in output.err


def test_success_prints_gemini_text(monkeypatch, image_path, capsys):
    payload = {"candidates": [{"content": {"parts": [
        {"text": "A blue bird."}, {"text": "On a branch."},
    ]}}]}
    calls = []

    def respond(request, timeout):
        calls.append(request)
        return io.BytesIO(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(look.urllib.request, "urlopen", respond)

    assert look.main(["look.py", str(image_path), "What is pictured?"]) == 0

    output = capsys.readouterr()
    assert output.out == "A blue bird.\nOn a branch.\n"
    assert output.err == ""
    assert len(calls) == 1


def test_http_error_returns_one(monkeypatch, image_path, capsys):
    def reject(request, timeout):
        raise HTTPError(request.full_url, 429, "Too Many Requests", {},
                        io.BytesIO(b"quota exceeded"))

    monkeypatch.setattr(look.urllib.request, "urlopen", reject)

    assert look.main(["look.py", str(image_path)]) == 1

    output = capsys.readouterr()
    assert output.out == ""
    assert "HTTP 429" in output.err
    assert "quota exceeded" in output.err
