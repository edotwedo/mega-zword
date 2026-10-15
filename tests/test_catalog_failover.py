"""OpenRouter aliases and coding failover: scripted models and HTTP fakes only."""
import json
import sys
from datetime import datetime, timedelta, timezone

import pytest

from megazword import agent, cli, config
from megazword.backends import default_backends
from megazword.free_apis import APIHTTPError, OpenAICompatibleBackend
from test_agent import Scripted, call
from test_free_apis import reply

_real_pace_call = agent.pace_call


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(agent, "pace_call", lambda *args: None)
    monkeypatch.setattr(agent.time, "sleep", lambda *args: None)


@pytest.mark.parametrize("name", ["kimi", "deepseek", "qwen-coder"])
def test_named_models_normal_and_edit(tmp_path, monkeypatch, name):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-test-key")
    path = tmp_path / "config.toml"
    path.write_text(f'[free.{name}]\nmodel = "custom:free"\n')
    cfg = config.load(path)
    cfg.log_path = tmp_path / "log.jsonl"
    backend = default_backends(free_models=cfg.free)[name]
    assert backend.trains_on_data
    assert config.DEFAULT_FREE[name].endswith(":free")
    requests = []

    def fake(request, **kwargs):
        requests.append(request)
        return reply("answer" if len(requests) == 1 else json.dumps(
            {"tool": "finish", "arguments": {"summary": "done"}}))

    monkeypatch.setattr("urllib.request.urlopen", fake)
    for flags in ([], ["-e"]):
        assert cli.main(["run", "job", "-m", name, *flags],
                        {name: backend}, cfg) == 0
    for request in requests:
        assert request.full_url == "https://openrouter.ai/api/v1/chat/completions"
        assert json.loads(request.data)["model"] == "custom:free"
    assert "tools" in json.loads(requests[1].data)


@pytest.mark.parametrize("error", [APIHTTPError(429), RuntimeError("API request timed out"),
                                  TimeoutError("timeout"), APIHTTPError(503)])
def test_failure_after_edit_preserves_task_files_and_tests(tmp_path, error, capsys):
    first = Scripted([call("write_file", path="calc.py", text="answer = 42\n"), error])
    first.name = "gemini-api"
    second = Scripted([call("read_file", path="calc.py"), call("run_tests")])
    second.name = "kimi"
    second.trains_on_data = True
    loop = agent.wrap(first, {"root": tmp_path, "test_command": (
        sys.executable, "-c", "import runpy; assert runpy.run_path('calc.py')['answer'] == 42")},
        fallback_backends=[second])
    result = loop.run("Fix calc and test it")
    assert result.ok, result.error
    assert (tmp_path / "calc.py").read_text() == "answer = 42\n"
    history = json.dumps(second.seen[0][0])
    assert "Fix calc and test it" in history and "calc.py" in history
    assert loop.backends_used == ["gemini-api", "kimi"]
    assert loop.requests_by_backend == {"gemini-api": 2, "kimi": 2}
    assert "continuing with kimi" in capsys.readouterr().err


def test_api_failover_retries_with_native_tools(tmp_path):
    first = Scripted([APIHTTPError(429, {"Retry-After": "300"})])
    first.name = "openrouter"
    second = Scripted([call("finish", summary="continued with tools")])
    second.name = "groq"
    loop = agent.wrap(first, {"root": tmp_path}, fallback_backends=[second])
    result = loop.run("Complete this coding task")
    assert result.ok and "continued with tools" in result.text
    assert second.seen[0][1] is not None
    assert loop.backends_used == ["openrouter", "groq"]


def test_cli_forced_order_skips_out_missing_and_duplicate_start(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    first = Scripted([APIHTTPError(429)])
    first.name = "kimi"
    out = Scripted([])
    out.name = "deepseek"
    missing = OpenAICompatibleBackend("gemini-api", key_env="NO_SUCH_TEST_KEY")
    next_backend = Scripted([call("finish", summary="continued")])
    next_backend.name = "qwen-coder"
    cfg = config.Config(log_path=tmp_path / "log.jsonl", agent={"failover_order": [
        "kimi", "deepseek", "gemini-api", "qwen-coder"]},
        out_until={"deepseek": datetime.now(timezone.utc) + timedelta(hours=1)})
    assert cli.main(["run", "job", "-e", "-m", "kimi"], {
        b.name: b for b in [first, out, missing, next_backend]}, cfg) == 0
    assert not out.seen
    record = json.loads(cfg.log_path.read_text().splitlines()[0])
    assert record["backends_used"] == ["kimi", "qwen-coder"]
    assert record["requests"] == 2


def test_exhaustion_is_bounded_leaves_edits(tmp_path):
    first = Scripted([call("write_file", path="a.py", text="saved"), TimeoutError("timeout")])
    second = Scripted([TimeoutError("timeout")])
    second.name = "cloudflare"
    loop = agent.wrap(first, {"root": tmp_path}, fallback_backends=[first, second])
    result = loop.run("fix a")
    assert not result.ok and "timeout" in result.error
    assert len(first.seen) == 2 and len(second.seen) == 1
    assert (tmp_path / "a.py").read_text() == "saved"


def test_failover_scrubs_history_for_training_provider(tmp_path):
    first = Scripted([TimeoutError("timeout")])
    second = Scripted([call("finish", summary="done")], trains=True)
    second.name = "kimi"
    loop = agent.wrap(first, {"root": tmp_path}, fallback_backends=[second])
    assert loop.run("job OPENROUTER_API_KEY=sk-test-secret-value").ok
    assert "sk-test-secret-value" not in json.dumps(second.seen)


@pytest.mark.parametrize("value", ['["codex"]', '["kimi", "kimi"]', '"kimi"'])
def test_invalid_failover_config(tmp_path, value):
    path = tmp_path / "config.toml"
    path.write_text(f"[agent]\nfailover_order = {value}\n")
    with pytest.raises(ValueError, match="failover_order"):
        config.load(path)


def test_empty_order_disables_switching(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    first = Scripted([TimeoutError("timeout")])
    second = Scripted([])
    second.name = "kimi"
    cfg = config.Config(log_path=tmp_path / "log.jsonl", agent={"failover_order": []})
    assert cli.main(["run", "job", "-e", "-m", "groq"],
                    {"groq": first, "kimi": second}, cfg) != 0
    assert not second.seen


def test_alias_pacing_shares_openrouter_quota(monkeypatch):
    reservations = []
    monkeypatch.setattr(agent, "write_atomic", lambda path, value: reservations.append(path))
    _real_pace_call("kimi", {"openrouter": 0.001}, agent.time.monotonic() + 10)
    _real_pace_call("qwen-coder", {"openrouter": 0.001}, agent.time.monotonic() + 10)
    assert len(reservations) == 2 and reservations[0] == reservations[1]
    assert reservations[0].name == "openrouter.json"


def test_switch_keeps_step_cap(tmp_path):
    first = Scripted([TimeoutError("timeout")])
    second = Scripted([call("list_files", glob="*")])
    second.name = "kimi"
    loop = agent.wrap(first, {"root": tmp_path, "max_steps": 2}, fallback_backends=[second])
    result = loop.run("job")
    assert not result.ok and "step cap" in result.error
    assert loop.request_count == 2


def test_expired_wall_cap_does_not_switch(tmp_path, monkeypatch):
    ticks = [100]
    monkeypatch.setattr(agent.time, "monotonic", lambda: ticks[0])
    first = Scripted([])
    def timeout(*args, **kwargs):
        ticks[0] = 111
        raise TimeoutError("timeout")
    monkeypatch.setattr(first, "chat", timeout)
    second = Scripted([])
    second.name = "kimi"
    loop = agent.wrap(first, {"root": tmp_path, "wall_timeout": 10}, fallback_backends=[second])
    assert not loop.run("job").ok
    assert not second.seen


def test_ollama_fallback_uses_same_files(tmp_path, monkeypatch):
    from megazword.backends import OllamaBackend
    first = Scripted([TimeoutError("timeout")])
    local = OllamaBackend("ollama", model="coder")
    monkeypatch.setattr(local, "available", lambda: True)
    seen = []
    def generate(prompt, model, url, **kwargs):
        seen.append((prompt, model, kwargs))
        return json.dumps({"tool": "finish", "arguments": {"summary": "local done"}})
    monkeypatch.setattr("megazword.ollama.generate", generate)
    loop = agent.wrap(first, {"root": tmp_path}, fallback_backends=[local])
    assert loop.run("same task").text == "local done"
    assert "same task" in seen[0][0] and seen[0][1] == "coder"
    assert seen[0][2]["json_format"]
