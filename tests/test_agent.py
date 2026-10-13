"""Scripted models only: no API keys, network or paid generations."""
import json
import sys
import time
from datetime import timedelta

import pytest

from megazword import agent, config, runlog
from megazword.free_apis import OpenAICompatibleBackend, ToolsUnsupported


def call(name, **args):
    return {"tool_calls": [{"id": "c1", "type": "function", "function": {
        "name": name, "arguments": json.dumps(args)}}]}


class Scripted(OpenAICompatibleBackend):
    def __init__(self, replies, trains=False):
        super().__init__("groq", trains_on_data=trains)
        self.replies = iter(replies)
        self.seen = []

    def available(self):
        return True

    def chat(self, messages, tools=None, timeout=None):
        self.seen.append((json.loads(json.dumps(messages)), tools, timeout))
        reply = next(self.replies)
        if isinstance(reply, Exception):
            raise reply
        return reply


def coding(tmp_path, replies, **kwargs):
    model = Scripted(replies, kwargs.pop("trains", False))
    return agent.wrap(model, {"root": tmp_path, **kwargs}), model


def test_edit_tests_finish(tmp_path):
    loop, _ = coding(tmp_path, [call("write_file", path="a.py", text="before"),
        call("replace_in_file", path="a.py", old="before", new="after"),
        call("run_tests"), call("finish", summary="Edited and tested.")],
        test_command=(sys.executable, "-c", "print('tests pass')"))
    result = loop.run("fix a")
    assert result.ok and result.text == "Edited and tested."
    assert (tmp_path / "a.py").read_text() == "after"
    assert loop.request_count == 4
    assert "exit code 0" in loop.model_backend.seen[-1][0][-1]["content"]


@pytest.mark.parametrize("path", ["../escape", ".git/config", ".env", ".env.local",
                                   "nested/.git/config", "C:/outside"])
def test_paths_refused(tmp_path, path):
    loop, model = coding(tmp_path, [call("write_file", path=path, text="bad"),
                                 call("finish", summary="refused")])
    assert loop.run("try").ok
    assert "refused" in model.seen[-1][0][-1]["content"]
    assert not list(tmp_path.iterdir())


def test_step_cap(tmp_path):
    loop, _ = coding(tmp_path, [call("list_files", glob="*")] * 3, max_steps=2)
    result = loop.run("keep going")
    assert not result.ok and "step cap" in result.error and loop.request_count == 2


@pytest.mark.parametrize("first", [ToolsUnsupported("tools"), {"content": "bad JSON"}])
def test_text_fallback_and_bad_json_recovery(tmp_path, first):
    loop, model = coding(tmp_path, [first, {"content": '```json\n' + json.dumps({
        "tool": "write_file", "arguments": {"path": "a", "text": "ok"}}) + '\n```'},
        {"content": json.dumps({"tool": "finish", "arguments": {"summary": "done"}})}])
    assert loop.run("job").ok
    assert model.seen[0][1] and model.seen[1][1] is None
    assert (tmp_path / "a").read_text() == "ok"


def test_secret_scrub_in_prompt_and_results(tmp_path):
    secret = "sk-" + "a" * 30
    (tmp_path / "config.txt").write_text(secret + "\npassword: hunter42\n")
    loop, model = coding(tmp_path, [call("read_file", path="config.txt"),
        call("finish", summary="done")], trains=True)
    assert loop.run("job " + secret).ok
    assert secret not in json.dumps(model.seen)
    assert "hunter42" not in json.dumps(model.seen)
    assert agent.scrub(secret) in json.dumps(model.seen)


def test_exact_replacement_refused(tmp_path):
    (tmp_path / "a").write_text("twice twice")
    loop, model = coding(tmp_path, [call("replace_in_file", path="a", old="twice", new="x"),
        call("finish", summary="refused")])
    assert loop.run("job").ok
    assert "exactly once" in model.seen[-1][0][-1]["content"]
    assert (tmp_path / "a").read_text() == "twice twice"


def test_symlink_escape_and_secret_alias(tmp_path):
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("private")
    secret = tmp_path / ".env"
    secret.write_text("private")
    try:
        (tmp_path / "link").symlink_to(outside)
        (tmp_path / "alias").symlink_to(secret)
    except OSError:
        pytest.skip("symlink privilege unavailable")
    loop, _ = coding(tmp_path, [])
    for path in ("link", "alias"):
        with pytest.raises(ValueError):
            loop._path(path)


def test_test_command_timeout(tmp_path):
    loop, _ = coding(tmp_path, [call("run_tests")], test_timeout=0.1,
                    test_command=(sys.executable, "-c", "import time; time.sleep(5)"))
    result = loop.run("test")
    assert not result.ok and "timed out" in result.error


def test_wall_timeout(tmp_path, monkeypatch):
    loop, model = coding(tmp_path, [call("finish", summary="too late")], wall_timeout=0.01)
    original = model.chat
    def slow(*args, **kwargs):
        time.sleep(0.02)
        return original(*args, **kwargs)
    monkeypatch.setattr(model, "chat", slow)
    assert "wall-clock" in loop.run("job").error
    assert model.seen[0][2] <= 0.01


def test_output_tail_and_no_model_commands(tmp_path):
    loop, model = coding(tmp_path, [call("run_tests", command="bad"), call("run_tests"),
        call("finish", summary="done")], max_chars=80,
        test_command=(sys.executable, "-c", "print('a'*500); print('TAIL')"))
    assert loop.run("job").ok
    assert "invalid tool arguments" in model.seen[1][0][-1]["content"]
    assert len(model.seen[2][0][-1]["content"]) <= 80
    assert "TAIL" in model.seen[2][0][-1]["content"]


@pytest.mark.parametrize("forced", [True, False])
def test_cli_edit_agent_logged(tmp_path, monkeypatch, capsys, forced):
    from megazword.cli import main
    from megazword.rater import Rating
    monkeypatch.chdir(tmp_path)
    model = Scripted([call("write_file", path="a", text="edit"),
                      call("finish", summary="done")])
    cfg = config.Config(log_path=tmp_path / "log.jsonl",
                        route={"easy": ["groq"]}, quality_check=False)
    argv = ["run", "job", "-e"] + (["-m", "groq"] if forced else [])
    assert main(argv, {"groq": model}, cfg, lambda _: Rating("easy", "test", "fake"), dict) == 0
    record = json.loads(cfg.log_path.read_text().splitlines()[0])
    assert record["requests"] == 2 and record["ok"]
    assert runlog.summarize(cfg.log_path, timedelta(hours=1))["groq"].runs == 2
    from megazword.stats import daily
    assert daily(cfg.log_path)[0].runs == 2
    assert "done" in capsys.readouterr().out


def test_config_agent(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[agent]\nmax_steps=5\ntext_protocol=true\ntest_command=["python", "check.py"]\n')
    assert config.load(path).agent["test_command"] == ("python", "check.py")
    path.write_text('[agent]\nmax_steps=-1\n')
    with pytest.raises(ValueError):
        config.load(path)


def test_ollama_edit_uses_text_protocol(tmp_path, monkeypatch):
    from megazword.backends import OllamaBackend
    seen = []
    def generate(prompt, model, url, **kwargs):
        seen.append((prompt, model, kwargs))
        return json.dumps({"tool": "finish", "arguments": {"summary": "local done"}})
    monkeypatch.setattr("megazword.ollama.generate", generate)
    loop = agent.wrap(OllamaBackend("ollama", model="local"), {"root": tmp_path})
    assert loop.run("job").text == "local done"
    assert seen[0][1] == "local" and seen[0][2]["json_format"]


def test_listing_filters_private_paths(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("private")
    (tmp_path / ".env").write_text("secret")
    (tmp_path / "visible.py").write_text("ok")
    loop, model = coding(tmp_path, [call("list_files", glob="*"), call("finish", summary="done")])
    assert loop.run("job").ok
    assert model.seen[-1][0][-1]["content"] == "visible.py"


def test_malformed_native_arguments_recover(tmp_path):
    bad = call("read_file", path="a")
    bad["tool_calls"][0]["function"]["arguments"] = "not json"
    loop, model = coding(tmp_path, [bad, call("finish", summary="done")])
    assert loop.run("job").ok
    assert "refused" in model.seen[-1][0][-1]["content"]
    assert model.seen[-1][1] is None


def test_http_native_calls_and_unsupported_fallback(tmp_path, monkeypatch):
    import io
    import urllib.error
    import urllib.request
    monkeypatch.setenv("TEST_KEY", "test-key")
    model = OpenAICompatibleBackend("groq", base_url="https://example.test/v1",
                                    key_env="TEST_KEY", model="fake")
    requests = []
    def urlopen(req, timeout):
        body = json.loads(req.data)
        requests.append(body)
        if len(requests) == 1:
            raise urllib.error.HTTPError(req.full_url, 400, "unsupported", {}, None)
        assert "tools" not in body
        message = {"content": json.dumps({"tool": "finish", "arguments": {"summary": "done"}})}
        return io.BytesIO(json.dumps({"choices": [{"message": message}]}).encode())
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    loop = agent.wrap(model, {"root": tmp_path})
    assert loop.run("job").ok
    assert len(requests) == 2 and "tools" in requests[0]


def test_http_native_response_preserved(tmp_path, monkeypatch):
    import io
    import urllib.request
    monkeypatch.setenv("TEST_KEY", "test-key")
    model = OpenAICompatibleBackend("groq", base_url="https://example.test/v1",
                                    key_env="TEST_KEY", model="fake")
    def urlopen(req, timeout):
        assert json.loads(req.data)["tools"] == agent.TOOLS
        return io.BytesIO(json.dumps({"choices": [{"message": {
            "role": "assistant", "content": None, **call("finish", summary="native done")}}]}).encode())
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert agent.wrap(model, {"root": tmp_path}).run("job").text == "native done"


def test_scrub_before_result_truncation(tmp_path):
    secret = "sk-" + "a" * 30
    (tmp_path / "a").write_text(secret)
    loop, model = coding(tmp_path, [call("read_file", path="a"),
        call("finish", summary="done")], trains=True, max_chars=8)
    assert loop.run("job").ok
    assert "sk-" not in model.seen[-1][0][-1]["content"]


def test_hardlink_refused(tmp_path):
    import os
    outside = tmp_path.parent / "hardlink-source"
    outside.write_text("private")
    try:
        os.link(outside, tmp_path / "alias")
    except OSError:
        pytest.skip("hard links unavailable")
    loop, _ = coding(tmp_path, [])
    with pytest.raises(ValueError, match="hard-linked"):
        loop._path("alias")
