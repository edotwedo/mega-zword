"""Pacing, quality and reviewer checks without network or real waits."""
import json
import sys
import subprocess
from pathlib import Path
from contextlib import contextmanager

import pytest

from megazword import agent, config
from megazword.agent_quality import check_tests
from test_agent import Scripted, call, coding


@pytest.fixture(autouse=True)
def no_real_pacing(monkeypatch):
    monkeypatch.setattr(agent, "DEFAULT_PACE", dict.fromkeys(agent.DEFAULT_PACE, 0))


def test_shared_provider_gap_and_independent_provider(tmp_path, monkeypatch):
    ticks = [100.0]
    sleeps = []
    monkeypatch.setattr(agent.time, "time", lambda: ticks[0])
    monkeypatch.setattr(agent.time, "monotonic", lambda: ticks[0])
    def sleep(seconds):
        sleeps.append(seconds)
        ticks[0] += seconds
    monkeypatch.setattr(agent.time, "sleep", sleep)
    agent.pace_call("groq", {"groq": 2}, 200)
    agent.pace_call("mistral", {"mistral": 2}, 200)
    # A fresh caller reads the same provider file, regardless of model/run.
    agent.pace_call("groq", {"groq": 2}, 200)
    assert sleeps == [2]
    assert float((config.HOME / "agent-pace/groq.json").read_text()) == 102


def test_tencent_model_aliases_share_provider_pacing(tmp_path, monkeypatch):
    ticks = [100.0]
    sleeps = []
    monkeypatch.setattr(agent.time, "time", lambda: ticks[0])
    monkeypatch.setattr(agent.time, "monotonic", lambda: ticks[0])
    def sleep(seconds):
        sleeps.append(seconds)
        ticks[0] += seconds
    monkeypatch.setattr(agent.time, "sleep", sleep)
    agent.pace_call("tencent-glm-5.3-flash", {"tencent": 2}, 200)
    agent.pace_call("tencent-kimi-k3", {"tencent": 2}, 200)
    agent.pace_call("tencent-deepseek-v4-pro", {"tencent": 2}, 200)
    agent.pace_call("tencent-deepseek-v4-flash-vision-exp", {"tencent": 2}, 200)
    assert sleeps == [2, 2, 2]
    assert float((config.HOME / "agent-pace/tencent.json").read_text()) == 106
    agent.pace_call("zai", {"zai": 2}, 200)
    agent.pace_call("zai-47", {"zai": 2}, 200)
    assert sleeps[-1] == 2  # both Z.ai models share one pace lock


def test_pacing_wall_cap_prevents_request(tmp_path, monkeypatch):
    monkeypatch.setattr(agent.time, "time", lambda: 100)
    monkeypatch.setattr(agent.time, "monotonic", lambda: 100)
    agent.pace_call("groq", {"groq": 2}, 200)
    loop, model = coding(tmp_path, [call("finish", summary="done")],
                         pace={"groq": 2}, wall_timeout=1)
    result = loop.run("job")
    assert not result.ok and "pacing" in result.error
    assert not model.seen and loop.request_count == 0


def test_pacing_fails_closed_when_lock_unavailable(monkeypatch):
    @contextmanager
    def unavailable(*args, **kwargs):
        yield False
    monkeypatch.setattr(agent, "locked", unavailable)
    with pytest.raises(TimeoutError, match="lock"):
        agent.pace_call("groq", {"groq": 2}, agent.time.monotonic() + 10)


def test_concurrent_processes_share_reservations(tmp_path):
    source = str(Path(agent.__file__).resolve().parents[1])
    script = '''
import json, sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from megazword import agent, config
config.HOME = Path(sys.argv[2])
ticks, sleeps = [100.0], []
agent.time.time = agent.time.monotonic = lambda: ticks[0]
def sleep(seconds):
    # filelock polls must yield to the other process; provider waits are fake.
    if seconds < 0.1:
        return
    sleeps.append(seconds)
    ticks[0] += seconds
agent.time.sleep = sleep
agent.pace_call('groq', {'groq': 2}, 200)
print(json.dumps(sleeps))
'''
    command = [sys.executable, "-c", script, source, str(tmp_path / "shared")]
    workers = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True) for _ in range(2)]
    results = []
    for worker in workers:
        out, err = worker.communicate(timeout=10)
        assert worker.returncode == 0, err
        results.append(json.loads(out))
    assert sorted(results) == [[], [2.0]]


def test_retries_are_paced_as_well(tmp_path, monkeypatch):
    from megazword.free_apis import APIHTTPError
    calls = []
    monkeypatch.setattr(agent, "pace_call", lambda name, pace, deadline: calls.append(name))
    monkeypatch.setattr(agent.time, "sleep", lambda seconds: None)
    loop, _ = coding(tmp_path, [APIHTTPError(429), call("finish", summary="done")])
    assert loop.run("job").ok
    assert calls == ["groq", "groq"]


def test_default_provider_gaps():
    # The fixture disables waits, so read the actual defaults from a fresh module.
    import ast
    module = ast.parse(Path(agent.__file__).read_text(encoding="utf-8"))
    defaults = next(ast.literal_eval(n.value) for n in module.body
                    if isinstance(n, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == "DEFAULT_PACE" for t in n.targets))
    assert defaults == {"gemini-api": 6, "mistral": 2, "groq": 2, "cloudflare": 1,
                        "openrouter": 3, "nvidia": 2, "zai": 2,
                        "cerebras": 2, "tencent": 2, "ollama": 0, "ovh": 31,
                        "ovh-120b": 31, "ovh-qwen": 31, "kilo": 18}


def test_cli_reviewer_uses_api_fake(tmp_path, monkeypatch, capsys):
    from megazword.cli import main
    from megazword.rater import Rating
    monkeypatch.chdir(tmp_path)
    model = Scripted([call("write_file", path="calc.py", text="answer = 3\n"),
                      call("finish", summary="done")])
    reviewer = Scripted([{"content": "REJECT calculation is wrong"}])
    reviewer.name = "mistral"
    cfg = config.Config(log_path=tmp_path / "log.jsonl", quality_check=False,
                        agent={"reviewer": "mistral"})
    code = main(["run", "job", "-e", "-m", "groq"],
                {"groq": model, "mistral": reviewer}, cfg,
                lambda _: Rating("easy", "test", "fake"), dict)
    assert code != 0 and len(reviewer.seen) == 1
    record = json.loads(cfg.log_path.read_text().splitlines()[0])
    assert not record["ok"] and record["requests"] == 3
    assert "calculation is wrong" in capsys.readouterr().err


@pytest.mark.parametrize("body,reason", [
    ("assert True", "nonconstant"), ("assert 1", "nonconstant"),
    ("assert 1 == 1", "nonconstant"), ("pass", "nonconstant"),
    ("value = 2\n    assert value == 2", "module under test"),
    ("assert len([1]) == 1", "module under test"),
])
def test_reject_vacuous_tests(body, reason):
    errors = check_tests("def test_fake():\n    " + body + "\n", "test_calc.py")
    assert any(reason in error for error in errors)


@pytest.mark.parametrize("text", [
    "from calc import add\ndef test_add():\n    assert add(1, 2) == 3\n",
    "import calc as c\ndef test_add():\n    actual = c.add(1,2)\n    assert actual == 3\n",
    "import pytest as p\nfrom calc import bad\ndef test_bad():\n    with p.raises(ValueError):\n        bad()\n",
    "from pytest import raises as r\nfrom calc import bad\ndef test_bad():\n    with r(ValueError):\n        bad()\n",
    "import pytest\nfrom calc import bad\ndef test_bad(): pytest.raises(ValueError, bad)\n",
    "from calc import add\ndef helper(): return add(1,2)\ndef test_add(): assert helper() == 3\n",
    "import pytest\nfrom calc import add\n@pytest.fixture\ndef result(): return add(1,2)\ndef test_add(result): assert result == 3\n",
    "from calc import Calc\ndef test_add():\n    calc = Calc()\n    assert calc.add(1,2) == 3\n",
    "from calc import add\nclass TestCalc:\n    async def test_add(self): assert await add(1,2) == 3\n",
])
def test_accept_meaningful_tests(text):
    assert check_tests(text, "test_calc.py") == []


@pytest.mark.parametrize("success", [call("finish", summary="done"), call("run_tests")])
def test_quality_rejects_then_model_repairs(tmp_path, success):
    good = "from calc import add\ndef test_add(): assert add(1,2) == 3\n"
    loop, model = coding(tmp_path, [
        call("write_file", path="test_calc.py", text="def test_fake(): assert True\n"),
        success, call("write_file", path="test_calc.py", text=good),
        call("run_tests")], test_command=(sys.executable, "-c", "pass"))
    result = loop.run("add tests")
    assert result.ok and loop.request_count == 4
    assert "quality gate rejected" in model.seen[2][0][-1]["content"]
    assert "test_fake" in model.seen[2][0][-1]["content"]


def test_quality_rejections_hit_step_cap(tmp_path):
    loop, _ = coding(tmp_path, [call("write_file", path="test_calc.py", text="bad syntax!"),
                              call("finish", summary="done")], max_steps=2)
    result = loop.run("add tests")
    assert not result.ok and "step cap" in result.error


def test_unchanged_tests_not_gated(tmp_path):
    text = "def test_old(): assert True\n"
    (tmp_path / "test_old.py").write_text(text)
    loop, _ = coding(tmp_path, [call("write_file", path="test_old.py", text=text),
                              call("finish", summary="done")])
    assert loop.run("tests").ok


def test_helper_and_conftest_files_do_not_need_test_functions():
    assert check_tests("def fixture(): return 2\n", "tests/helpers.py") == []
    assert check_tests("def fixture(): return 2\n", "tests/conftest.py") == []
    assert "no test functions" in check_tests("", "tests/test_removed.py")[0]


def test_new_empty_test_file_is_gated(tmp_path):
    loop, _ = coding(tmp_path, [call("write_file", path="test_empty.py", text=""),
                              call("finish", summary="done")], max_steps=2)
    assert not loop.run("add tests").ok


def test_reviewer_sees_new_empty_file(tmp_path):
    reviewer = Scripted([{"content": "ACCEPT"}])
    loop, _ = coding(tmp_path, [call("write_file", path="empty.py", text=""),
                              call("finish", summary="done")], reviewer="groq",
                         reviewer_backend=reviewer)
    assert loop.run("job").ok
    assert "+++ empty.py\n[new empty file]" in reviewer.seen[0][0][0]["content"]


@pytest.mark.parametrize("verdict,ok", [("ACCEPT", True), ("REJECT missing edge cases", False),
                                       ("", False), ("maybe", False)])
def test_reviewer_one_read_only_call_and_new_file_diff(tmp_path, verdict, ok):
    reviewer = Scripted([{"content": verdict}])
    loop, _ = coding(tmp_path, [call("write_file", path="calc.py", text="answer = 3\n"),
                              call("finish", summary="done")], reviewer="groq",
                         reviewer_backend=reviewer)
    result = loop.run("job")
    assert result.ok == ok and len(reviewer.seen) == 1
    messages, tools, timeout = reviewer.seen[0]
    assert tools is None and "+answer = 3" in messages[0]["content"]
    assert "calc.py" in messages[0]["content"] and timeout <= 60
    assert loop.request_count == 3
    if verdict.startswith("REJECT"):
        assert "missing edge cases" in result.error


def test_missing_reviewer_fails_run(tmp_path):
    loop, _ = coding(tmp_path, [call("finish", summary="done")], reviewer="unknown")
    assert "reviewer unavailable" in loop.run("job").error


def test_reviewer_failure_is_one_call_without_retry(tmp_path):
    reviewer = Scripted([RuntimeError("review failed")])
    loop, _ = coding(tmp_path, [call("finish", summary="done")], reviewer="groq",
                         reviewer_backend=reviewer)
    result = loop.run("job")
    assert not result.ok and "review failed" in result.error
    assert len(reviewer.seen) == 1 and loop.request_count == 2


def test_reviewer_secret_scrub_and_backend_timeout(tmp_path):
    secret = "sk-" + "z" * 30
    reviewer = Scripted([{"content": "ACCEPT"}], trains=True)
    reviewer.timeout = 7
    loop, _ = coding(tmp_path, [call("write_file", path="calc.py", text=secret),
                              call("finish", summary="done")], reviewer="groq",
                         reviewer_backend=reviewer)
    assert loop.run("job").ok
    assert secret not in json.dumps(reviewer.seen)
    assert reviewer.seen[0][2] == 7


@pytest.mark.parametrize("settings", [
    '[agent]\nreviewer="groq"\n[agent.pace]\ngroq=0.5\nollama=0\n',
    '[agent.pace]\ngemini-api=6\n',
])
def test_config_pace_and_reviewer(tmp_path, settings):
    path = tmp_path / "config.toml"
    path.write_text(settings)
    assert config.load(path).agent["pace"]


@pytest.mark.parametrize("settings", ['[agent.pace]\ngroq=-1', '[agent.pace]\ngroq=true',
    '[agent.pace]\ngroq=inf', '[agent.pace]\nunknown=2', '[agent]\nreviewer=1'])
def test_config_rejects_invalid_settings(tmp_path, settings):
    path = tmp_path / "config.toml"
    path.write_text(settings)
    with pytest.raises(ValueError):
        config.load(path)
