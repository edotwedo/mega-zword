"""Scripted models only: no API keys, network or paid generations."""
import json
import sys
import time
from datetime import timedelta

import pytest

from megazword import agent, config, runlog
from megazword.free_apis import OpenAICompatibleBackend, ToolsUnsupported


@pytest.fixture(autouse=True)
def no_real_pacing(monkeypatch):
    monkeypatch.setattr(agent, "DEFAULT_PACE", dict.fromkeys(agent.DEFAULT_PACE, 0))


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
    reviewer = kwargs.pop("reviewer_backend", None)
    return agent.wrap(model, {"root": tmp_path, **kwargs}, reviewer), model


def test_edit_tests_finish(tmp_path):
    loop, _ = coding(tmp_path, [call("write_file", path="a.py", text="before"),
        call("replace_in_file", path="a.py", old="before", new="after"),
        call("run_tests"), call("finish", summary="Edited and tested.")],
        test_command=(sys.executable, "-c", "print('tests pass')"))
    result = loop.run("fix a")
    assert result.ok and result.text == "tests pass"
    assert (tmp_path / "a.py").read_text() == "after"
    assert loop.request_count == 3


def test_coding_agent_can_fetch_bounded_public_url(monkeypatch, tmp_path):
    from megazword import public_fetch
    monkeypatch.setattr(public_fetch, "fetch_public_url", lambda url: "Fetched public page: page text")
    loop, model = coding(tmp_path, [call("fetch_public_url", url="https://example.com/docs"),
                                    call("finish", summary="The docs describe the API.")])
    result = loop.run("Read the public API docs and summarize them")
    assert result.ok
    assert "Fetched public page: page text" in model.seen[-1][0][-1]["content"]
    assert "fetch_public_url" in {tool["function"]["name"] for tool in model.seen[0][1]}


def test_read_only_review_reads_source_and_refuses_writes_and_tests(tmp_path):
    (tmp_path / 'source.py').write_text('def route():\n    return "free"\n')
    loop, model = coding(tmp_path, [call('finish', summary='Generic guesses'),
        call('write_file', path='source.py', text='damaged'), call('run_tests'),
        call('read_file', path='source.py'),
        call('finish', summary='source.py:2 returns a free route; inspect fallback handling next.')], read_only=True)
    result = loop.run('Review the code without edits')
    assert result.ok and 'source.py:2' in result.text
    assert (tmp_path / 'source.py').read_text() == 'def route():\n    return "free"\n'
    assert {t['function']['name'] for t in model.seen[0][1]} == {'list_files','read_file','finish'}
    history = str(model.seen[-1][0])
    assert 'Read source files before finishing' in history
    assert 'read-only review: writes and commands are unavailable' in history
    assert '2:     return' in history


def test_cli_review_has_no_subscription_or_reviewer_fallback(tmp_path, monkeypatch, capsys):
    from megazword.cli import main
    from megazword.rater import Rating
    from tests.test_cli import FakeBackend
    monkeypatch.chdir(tmp_path)
    (tmp_path/'a.py').write_text('x = 1\n')
    model = Scripted([call('read_file', path='a.py'), call('finish', summary='a.py:1 defines x.')])
    paid = FakeBackend('codex', fail=True)
    cfg = config.Config(log_path=tmp_path/'log.jsonl', route={'hard':['codex','groq']},
                        quality_check=False, agent={'reviewer':'claude'})
    assert main(['run','review code; no paid usage','--review'], {'codex':paid,'groq':model},
                cfg, lambda _: Rating('hard','test','fake'), dict) == 0
    last = json.loads((config.HOME/'last_run.json').read_text())
    assert last['chain'] == ['groq']
    assert 'a.py:1' in capsys.readouterr().out


def test_old_dashboard_audit_prompt_gets_tools_at_cli_entrypoint(tmp_path, monkeypatch):
    from megazword import cli
    monkeypatch.chdir(tmp_path)
    model = Scripted([call('read_file', path='routing.py', start=1, end=45),
                      call('finish', summary='routing.py:8 defines the Tencent backend group.')])
    prompt = "i want you to do a full audit of your code.  Then i want you to suggest possible upgrade paths."
    cfg = config.Config(log_path=tmp_path/'log.jsonl', quality_check=False)
    # Exact old-server shape: no --review, --review-root or --free-only.
    assert cli.main(['run',prompt,'-p','mega-zword','-m','groq'], {'groq':model}, cfg) == 0
    last = json.loads((config.HOME/'last_run.json').read_text())
    assert last['policy']['review'] and last['policy']['free_only']
    assert last['policy']['review_root'] == str(__import__('pathlib').Path(cli.__file__).resolve().parent)
    assert "not the model's weights" in last['sent']
    assert 'routing.py:8' in last['answer']


def test_no_paid_prompt_rejects_forced_subscription_before_call(tmp_path, capsys):
    from megazword.cli import main
    from tests.test_cli import FakeBackend
    paid = FakeBackend('codex', fail=True)
    cfg = config.Config(log_path=tmp_path/'log.jsonl')
    assert main(['run',"dont' use any paid usage",'-m','codex'], {'codex':paid}, cfg) == 2
    assert not cfg.log_path.exists()
    assert 'free-only request excludes' in capsys.readouterr().err


def test_free_only_refuses_paid_openrouter_override(tmp_path):
    from megazword.cli import main
    model = Scripted([])
    model.base_url = 'https://openrouter.ai/api/v1'
    model.model = 'vendor/paid-model'
    assert main(['run','no paid usage','-m','groq'], {'groq':model},
                config.Config(log_path=tmp_path/'log.jsonl')) == 2
    assert model.seen == []


def test_retry_does_not_reintroduce_paid_fallbacks(tmp_path, capsys):
    from megazword.cli import save_last_run, retry_last
    from types import SimpleNamespace
    from tests.test_cli import FakeBackend
    save_last_run('no paid usage','no paid usage',['groq'],'groq','answer','test','hard',
                  policy={'free_only':True})
    model = Scripted([])
    paid = FakeBackend('codex', fail=True)
    cfg = config.Config(log_path=tmp_path/'log.jsonl',route={'hard':['codex','groq']})
    assert retry_last(SimpleNamespace(model=None),{'groq':model,'codex':paid},cfg) == 1
    assert model.seen == [] and not cfg.log_path.exists()
    assert 'no AI left to try' in capsys.readouterr().err


def test_review_free_policy_accepts_all_configured_tencent_identities():
    from megazword.backends import default_backends
    from megazword.routing import TENCENT_BACKENDS
    from megazword.request_mode import free_backend
    models = default_backends()
    assert all(free_backend(models[name]) for name in TENCENT_BACKENDS)


def test_retry_upgrades_legacy_prompt_only_code_review(tmp_path, monkeypatch):
    from megazword import cli
    from types import SimpleNamespace
    cli.save_last_run('access your code','access your code',['groq'],'groq','generic answer','mega-zword','hard')
    calls = []
    monkeypatch.setattr(cli, 'main', lambda argv, **kw: calls.append(argv) or 0)
    assert cli.retry_last(SimpleNamespace(model=None),{},config.Config()) == 0
    assert '--review' in calls[0] and '--free-only' in calls[0]
    assert calls[0][calls[0].index('--review-root')+1] == str(__import__('pathlib').Path(cli.__file__).resolve().parent)


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
    assert result.error.endswith("tool calls: list_files 2")


def test_agent_prompt_tracks_remaining_tool_steps_without_rewriting_history(tmp_path):
    (tmp_path / "source.txt").write_text("source")
    loop, model = coding(tmp_path, [call("read_file", path="source.txt"),
                                   call("finish", summary="done")], max_steps=2)

    assert loop.run("inspect source").ok

    first_system = model.seen[0][0][0]["content"]
    second_system = model.seen[1][0][0]["content"]
    assert "2 tool steps remaining" in first_system
    assert "1 tool steps remaining" in second_system
    # Runtime guidance is ephemeral; it does not accumulate in the conversation.
    assert first_system.count("Execution budget:") == 1
    assert second_system.count("Execution budget:") == 1


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
    loop, model = coding(tmp_path, [call("finish", summary="too late")], wall_timeout=2)
    original = model.chat
    def slow(*args, **kwargs):
        time.sleep(2.02)
        return original(*args, **kwargs)
    monkeypatch.setattr(model, "chat", slow)
    assert "wall-clock" in loop.run("job").error
    # The call receives the remaining wall-clock budget, not the slower model delay.
    assert model.seen[0][2] <= 2 + 1e-8


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
    assert seen[0][2]["messages"][0]["role"] == "system"


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
        # A job with no web hint omits the fetch tool.
        assert json.loads(req.data)["tools"] == [
            t for t in agent.TOOLS if t["function"]["name"] != "fetch_public_url"]
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


def test_auto_finish_uses_last_assistant_text(tmp_path):
    reply = call("run_tests")
    reply["content"] = "Fixed the addition bug."
    loop, _ = coding(tmp_path, [call("write_file", path="calc.py", text="fixed"), reply],
                    test_command=(sys.executable, "-c", "pass"))
    assert loop.run("fix addition").text == "Fixed the addition bug."
    assert loop.request_count == 2


@pytest.mark.parametrize("edited,exit_code", [(False, 0), (True, 1)])
def test_no_auto_finish_without_edit_and_passing_tests(tmp_path, edited, exit_code):
    replies = ([call("write_file", path="calc.py", text="fixed")] if edited else [])
    replies += [call("run_tests"), call("finish", summary="explicit finish")]
    loop, model = coding(tmp_path, replies,
        test_command=(sys.executable, "-c", f"raise SystemExit({exit_code})"))
    assert loop.run("fix addition").text == "explicit finish"
    assert f"exit code {exit_code}" in model.seen[-1][0][-1]["content"]


def test_repeated_call_nudges_finish(tmp_path):
    loop, model = coding(tmp_path, [call("list_files", glob="*")] * 3 +
                         [call("finish", summary="done")])
    assert loop.run("job").ok
    assert "Finish now" in model.seen[-1][0][-1]["content"]


def test_repeated_calls_in_batch_nudge_after_all_tool_results(tmp_path):
    batch = {"tool_calls": [call("list_files", glob="*")["tool_calls"][0] for _ in range(3)]
                          + call("read_file", path="calc.py")["tool_calls"]}
    (tmp_path / "calc.py").write_text("code")
    loop, model = coding(tmp_path, [batch, call("finish", summary="done")])
    assert loop.run("job").ok
    history = model.seen[-1][0]
    assert "Finish now" in history[-1]["content"]
    assert [m["role"] for m in history[-5:-1]] == ["tool"] * 4


@pytest.mark.parametrize("test_alias", [True, False])
def test_test_file_symlink_edits_refused(tmp_path, test_alias):
    target = tmp_path / ("calc.py" if test_alias else "test_calc.py")
    alias = tmp_path / ("test_calc.py" if test_alias else "calc.py")
    target.write_text("original")
    try:
        alias.symlink_to(target)
    except OSError:
        pytest.skip("symlink privilege unavailable")
    loop, model = coding(tmp_path, [call("write_file", path=alias.name, text="changed"),
                                  call("finish", summary="done")])
    assert loop.run("fix addition").ok
    assert "job does not mention tests" in model.seen[-1][0][-1]["content"]
    assert target.read_text() == "original"


@pytest.mark.parametrize("path", ["test_calc.py", "calc_test.py", "tests/calc.py",
                                   "nested/tests/calc.py", "TEST_CALC.PY"])
@pytest.mark.parametrize("tool", ["write_file", "replace_in_file"])
def test_test_edits_refused_without_job_permission(tmp_path, path, tool):
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("original")
    args = {"text": "changed"} if tool == "write_file" else {"old": "original", "new": "changed"}
    loop, model = coding(tmp_path, [call(tool, path=path, **args), call("finish", summary="done")])
    assert loop.run("fix addition").ok
    assert "job does not mention tests" in model.seen[-1][0][-1]["content"]
    assert target.read_text() == "original"


@pytest.mark.parametrize("job", ["Add tests", "Fix the TEST", "Run pytest", "Improve testing"])
def test_test_edits_allowed_when_job_mentions_tests(tmp_path, job):
    text = "from calc import add\ndef test_add():\n    assert add(1, 2) == 3\n"
    loop, _ = coding(tmp_path, [call("write_file", path="tests/test_calc.py", text=text),
                              call("finish", summary="done")])
    assert loop.run(job).ok
    assert (tmp_path / "tests/test_calc.py").read_text() == text


@pytest.mark.parametrize("code", [429, 500, 502, 503])
def test_transient_http_retries(tmp_path, monkeypatch, code):
    from megazword.free_apis import APIHTTPError
    sleeps = []
    monkeypatch.setattr(agent.time, "sleep", sleeps.append)
    loop, _ = coding(tmp_path, [APIHTTPError(code)] * 3 + [call("finish", summary="done")], max_steps=1)
    assert loop.run("job").ok
    assert sleeps == ([120, 120, 120] if code == 429 else [2, 5, 10])
    assert loop.request_count == 4


def test_transient_http_retry_exhaustion(tmp_path, monkeypatch):
    from megazword.free_apis import APIHTTPError
    sleeps = []
    monkeypatch.setattr(agent.time, "sleep", sleeps.append)
    loop, _ = coding(tmp_path, [APIHTTPError(503)] * 4)
    result = loop.run("job")
    assert not result.ok and result.error == "API HTTP error 503"
    assert sleeps == [2, 5, 10] and loop.request_count == 4


def test_real_chat_preserves_retry_status(tmp_path, monkeypatch):
    import io
    import urllib.error
    import urllib.request
    monkeypatch.setenv("TEST_KEY", "test-key")
    sleeps, requests = [], []
    monkeypatch.setattr(agent.time, "sleep", sleeps.append)
    def urlopen(req, timeout):
        requests.append(json.loads(req.data))
        if len(requests) <= 2:
            raise urllib.error.HTTPError(req.full_url, 503, "private body", {}, None)
        return io.BytesIO(json.dumps({"choices": [{"message": call("finish", summary="done")}]}).encode())
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    model = OpenAICompatibleBackend("gemini-api", base_url="https://example.test/v1",
                                    key_env="TEST_KEY", model="fake")
    loop = agent.wrap(model, {"root": tmp_path, "max_steps": 1})
    assert loop.run("job").ok
    assert sleeps == [2, 5] and loop.request_count == 3


def test_http_auth_error_is_not_retried(tmp_path, monkeypatch):
    from megazword.free_apis import APIHTTPError
    sleeps = []
    monkeypatch.setattr(agent.time, "sleep", sleeps.append)
    loop, _ = coding(tmp_path, [APIHTTPError(401)])
    assert not loop.run("job").ok
    assert not sleeps and loop.request_count == 1


def test_retry_obeys_wall_cap(tmp_path, monkeypatch):
    from megazword.free_apis import APIHTTPError
    sleeps = []
    monkeypatch.setattr(agent.time, "sleep", sleeps.append)
    loop, _ = coding(tmp_path, [APIHTTPError(503)], wall_timeout=1)
    assert "wall-clock cap" in loop.run("job").error
    assert not sleeps


def test_rate_limit_beyond_wall_cap_keeps_retry_after_error(tmp_path, monkeypatch):
    from megazword.free_apis import APIHTTPError
    sleeps = []
    monkeypatch.setattr(agent.time, "sleep", sleeps.append)
    loop, _ = coding(tmp_path, [APIHTTPError(429, {"Retry-After": "300"})],
                     wall_timeout=1)
    error = loop.run("job").error
    assert "HTTP error 429: rate limited" in error
    assert "try again in 5 minutes" in error
    assert not sleeps


def test_ollama_missing_model_uses_first_installed(tmp_path, monkeypatch, capsys):
    import io
    import urllib.error
    import urllib.request
    from megazword.backends import OllamaBackend
    seen = []
    def urlopen(req, timeout):
        url = req if isinstance(req, str) else req.full_url
        seen.append((url, timeout))
        if url.endswith("/api/tags"):
            return io.BytesIO(json.dumps({"models": [{"name": "qwen2.5:1.5b"},
                                                    {"name": "another"}]}).encode())
        body = json.loads(req.data)
        if body["model"] == "missing":
            raise urllib.error.HTTPError(url, 404, "missing", {}, None)
        assert body["model"] == "qwen2.5:1.5b"
        tool = "list_files" if len(seen) == 3 else "finish"
        args = {"glob": "*"} if tool == "list_files" else {"summary": "done"}
        return io.BytesIO(json.dumps({"message": {"content": json.dumps({"tool": tool, "arguments": args})}}).encode())
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    model = OllamaBackend("ollama", model="missing")
    loop = agent.wrap(model, {"root": tmp_path})
    assert loop.run("job").ok
    assert loop.request_count == 3
    assert sum(url.endswith("/api/tags") for url, _ in seen) == 1
    assert "using installed model qwen2.5:1.5b" in capsys.readouterr().out
    assert model.model == "missing"


def test_ollama_missing_model_no_installed_models(tmp_path, monkeypatch):
    import urllib.error
    from megazword.backends import OllamaBackend
    def missing(*args, **kwargs):
        raise urllib.error.HTTPError("http://local/api/generate", 404, "missing", {}, None)
    monkeypatch.setattr("megazword.ollama.generate", missing)
    monkeypatch.setattr("megazword.ollama.installed_models", lambda *args, **kwargs: [])
    loop = agent.wrap(OllamaBackend("ollama", model="missing"), {"root": tmp_path})
    assert "no fallback model available" in loop.run("job").error


def test_test_env_isolated_and_output_scrubbed_for_nontrainer(tmp_path, monkeypatch):
    monkeypatch.setenv("UNUSUAL_PRIVATE_TOKEN", "opaque-private-value")
    monkeypatch.setenv("MY_PASSWORD", "another-private-value")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    (tmp_path / "pytest.py").write_text("raise RuntimeError('shadow pytest imported')")
    secret = "sk-" + "z" * 30
    code = ("import os,sys; assert not any(k in os.environ for k in "
            "['UNUSUAL_PRIVATE_TOKEN','MY_PASSWORD','PYTHONPATH']); "
            "assert sys.flags.isolated; print('" + secret + "')")
    loop, model = coding(tmp_path, [call("run_tests"), call("finish", summary="done")],
                         test_command=(sys.executable, "-c", code))
    assert loop.run("job").ok
    output = model.seen[-1][0][-1]["content"]
    assert "exit code 0" in output and secret not in output
    assert agent.scrub(secret) in output


def test_python_test_module_cannot_be_shadowed(tmp_path):
    (tmp_path / "pytest.py").write_text("print('SHADOW_IMPORTED'); raise SystemExit(0)")
    (tmp_path / "test_probe.py").write_text("def test_probe(): assert True")
    loop, model = coding(tmp_path, [call("run_tests"), call("finish", summary="done")],
                         test_command=(sys.executable, "-m", "pytest", "-q"))
    assert loop.run("job").ok
    output = model.seen[-1][0][-1]["content"]
    assert "1 passed" in output and "SHADOW_IMPORTED" not in output


def test_conftest_cannot_print_parent_credentials(tmp_path, monkeypatch):
    names = ["GROQ_API_KEY", "CLOUDFLARE_API_TOKEN", "MY_SECRET", "MY_PASSWORD", "lowercase_key"]
    for name in names:
        monkeypatch.setenv(name, "opaque-parent-credential")
    (tmp_path / "conftest.py").write_text("import os; print(dict(os.environ))")
    (tmp_path / "test_probe.py").write_text("def test_probe(): assert True")
    loop, model = coding(tmp_path, [call("run_tests"), call("finish", summary="done")],
                         test_command=(sys.executable, "-m", "pytest", "-q", "-s"))
    assert loop.run("job").ok
    output = model.seen[-1][0][-1]["content"]
    assert "1 passed" in output and "opaque-parent-credential" not in output


def test_test_output_scrub_before_tail_truncation(tmp_path):
    secret = "sk-" + "z" * 100
    loop, model = coding(tmp_path, [call("run_tests"), call("finish", summary="done")],
                         max_chars=80, test_command=(sys.executable, "-c", f"print('{secret}')"))
    assert loop.run("job").ok
    output = model.seen[-1][0][-1]["content"]
    assert "zzzz" not in output and agent.scrub(secret) in output


@pytest.mark.parametrize("pattern", ["*.py", "nested/?.py", "**/*.py"])
def test_glob_patterns_are_not_resolved(tmp_path, monkeypatch, pattern):
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested/a.py").write_text("ok")
    original = agent.AgentBackend._path
    def checked(self, value):
        assert "*" not in value and "?" not in value
        return original(self, value)
    monkeypatch.setattr(agent.AgentBackend, "_path", checked)
    loop, model = coding(tmp_path, [call("list_files", glob=pattern), call("finish", summary="done")])
    assert loop.run("job").ok
    assert "nested/a.py" in model.seen[-1][0][-1]["content"]


@pytest.mark.parametrize("pattern", ["../*", "C:/*", "nested\\*", "bad\0*", "/*"])
def test_unsafe_glob_patterns_refused(tmp_path, pattern):
    loop, model = coding(tmp_path, [call("list_files", glob=pattern), call("finish", summary="done")])
    assert loop.run("job").ok
    assert "tool refused" in model.seen[-1][0][-1]["content"]


def test_call_timeout_does_not_cap_run(tmp_path, monkeypatch):
    loop, model = coding(tmp_path, [call("list_files", glob="*"), call("finish", summary="done")],
                         call_timeout=3, wall_timeout=20)
    loop.timeout = 1
    ticks = iter(range(100))
    monkeypatch.setattr(agent.time, "monotonic", lambda: next(ticks))
    assert loop.run("job").ok
    assert all(timeout == 3 for _, _, timeout in model.seen)


@pytest.mark.parametrize("reply", [{"content": []}, {"content": {"text": "bad"}},
    {"tool_calls": "bad"}, {"tool_calls": {}}, {"tool_calls": [None] * 9},
    {"tool_calls": [None]}, ["bad"]])
def test_invalid_model_replies_recover(tmp_path, reply):
    loop, model = coding(tmp_path, [reply, call("finish", summary="recovered")])
    assert loop.run("job").text == "recovered"
    assert "Invalid reply" in model.seen[-1][0][-1]["content"] or "tool refused" in model.seen[-1][0][-1]["content"]


@pytest.mark.parametrize("tool", ["write_file", "replace_in_file"])
def test_write_size_cap_in_bytes(tmp_path, tool):
    (tmp_path / "a.py").write_text("original")
    args = {"text": "\u00e9" * 100001} if tool == "write_file" else {"old": "original", "new": "\u00e9" * 100001}
    loop, model = coding(tmp_path, [call(tool, path="a.py", **args), call("finish", summary="done")])
    assert loop.run("job").ok
    assert "200,000 bytes" in model.seen[-1][0][-1]["content"]
    assert (tmp_path / "a.py").read_text() == "original"


def test_cloudflare_rejection_flattens_and_trims_history(tmp_path):
    from megazword.free_apis import APIHTTPError
    (tmp_path / "a.py").write_text("x" * 10000)
    loop, model = coding(tmp_path, [call("read_file", path="a.py"), ToolsUnsupported("schema"),
        APIHTTPError(400, reason="context too long"), call("finish", summary="done")])
    loop.name = "cloudflare"
    model.name = "cloudflare"
    assert loop.run("job").ok
    assert model.seen[2][1] is None and model.seen[3][1] is None
    history = model.seen[3][0]
    assert all(set(m) == {"role", "content"} for m in history)
    assert all(len(m["content"]) <= 2000 for m in history[2:-1])
    assert history[1]["content"] == "job"


def test_cloudflare_invalid_request_recovery_is_bounded(tmp_path):
    from megazword.free_apis import APIHTTPError
    loop, model = coding(tmp_path, [APIHTTPError(400, reason="context too long")] * 2)
    loop.name = "cloudflare"
    model.name = "cloudflare"
    result = loop.run("job")
    assert not result.ok and "context too long" in result.error
    assert loop.request_count == 2
