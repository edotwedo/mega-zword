import io
import json

from megazword import ollama


def test_coding_chat_uses_roles_instead_of_serialized_prompt(monkeypatch):
    seen = []
    messages = [{"role": "system", "content": "Use tools"},
                {"role": "user", "content": "Fix a spelling error"}]
    def urlopen(request, timeout):
        seen.append((request.full_url, json.loads(request.data), timeout))
        return io.BytesIO(json.dumps({"message": {"content": '{"tool":"finish"}'}}).encode())
    monkeypatch.setattr(ollama.urllib.request, "urlopen", urlopen)
    assert ollama.generate("unused", "coder", messages=messages, json_format=True) == '{"tool":"finish"}'
    assert seen[0][0].endswith("/api/chat")
    assert seen[0][1]["messages"] == messages
    assert "prompt" not in seen[0][1] and seen[0][1]["format"] == "json"


def test_plain_generation_keeps_original_endpoint(monkeypatch):
    seen = []
    def urlopen(request, timeout):
        seen.append((request.full_url, json.loads(request.data)))
        return io.BytesIO(b'{"response":"answer"}')
    monkeypatch.setattr(ollama.urllib.request, "urlopen", urlopen)
    assert ollama.generate("rate this", "rater") == "answer"
    assert seen[0][0].endswith("/api/generate")
    assert seen[0][1]["prompt"] == "rate this" and "messages" not in seen[0][1]
