"""Real local control files, scripted models, and no provider calls."""
import json
import sys
import threading

import pytest

from megazword import agent, config, dashboard
from megazword.free_apis import OpenAICompatibleBackend
from megazword.run_control import Control, ENV


def test_pause_resume_and_queue_are_consumed_once(tmp_path, monkeypatch):
    control = Control(tmp_path / "control")
    control.request("pause")
    control.request("instruct", "Use the new filename")
    entered = threading.Event()
    original = control.publish

    def publish(phase, **details):
        original(phase, **details)
        if phase == "paused":
            entered.set()

    monkeypatch.setattr(control, "publish", publish)
    result = []
    worker = threading.Thread(target=lambda: result.append(control.checkpoint()))
    worker.start()
    try:
        assert entered.wait(3)
        assert control.view()["phase"] == "paused"
        control.request("resume")
        worker.join(3)
        assert not worker.is_alive()
        assert result[0][0] == ["Use the new filename"]
        assert result[0][1] > 0
        assert control.checkpoint()[0] == []
    finally:
        control.request("resume")
        worker.join(3)


def test_stop_and_invalid_actions(tmp_path):
    control = Control(tmp_path)
    with pytest.raises(ValueError):
        control.request("execute")
    with pytest.raises(ValueError):
        control.request("instruct", " ")
    control.request("stop")
    with pytest.raises(RuntimeError, match="stopped by user"):
        control.checkpoint()


def test_activity_is_bounded_and_scrubs_env_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "private-value-for-test")
    control = Control(tmp_path)
    for i in range(45):
        control.publish("tool", file="private-value-for-test", requests=i)
    view = control.view()
    assert len(view["events"]) == 40
    assert view["requests"] == "44"
    assert "private-value-for-test" not in json.dumps(view)


def test_control_env_refuses_outside_home(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV, str(tmp_path / "outside"))
    with pytest.raises(ValueError, match="under Mega Zword home"):
        Control.from_env()


def call(name, **args):
    return {"tool_calls": [{"id": "c1", "type": "function", "function": {
        "name": name, "arguments": json.dumps(args)}}]}


def test_instruction_before_write_skips_old_tool_and_replans(tmp_path, monkeypatch):
    control = Control(config.HOME / "run-controls" / "test")
    seen = []

    class Model(OpenAICompatibleBackend):
        def available(self):
            return True

        def chat(self, messages, tools=None, timeout=None):
            seen.append(json.loads(json.dumps(messages)))
            if len(seen) == 1:
                control.request("instruct", "Write new.py instead")
                return call("write_file", path="old.py", text="old")
            if len(seen) == 2:
                return call("write_file", path="new.py", text="new")
            return call("run_tests")

    model = Model("groq", model="scripted")
    loop = agent.wrap(model, {"root": tmp_path, "control": control, "pace": {"groq": 0},
                             "test_command": (sys.executable, "-c", "print('ok')")})
    result = loop.run("write a file")
    assert result.ok, result.error
    assert not (tmp_path / "old.py").exists()
    assert (tmp_path / "new.py").read_text() == "new"
    assert seen[1][-2]["role"] == "tool"
    assert seen[1][-2]["tool_call_id"] == "c1"
    assert "Write new.py instead" in seen[1][-1]["content"]
    phases = [event["phase"] for event in control.view()["events"]]
    assert "file edited" in phases and "tests finished" in phases
    assert phases[-1] == "finished"


def test_dashboard_edit_requires_one_free_bot(tmp_path):
    class Fake:
        def available(self):
            return True

    captured = []

    def launch(*args):
        captured.append(args)
        return object()

    app = dashboard.App(config.Config(), "test", backends={"groq": Fake(), "codex": Fake()}, launcher=launch)
    app.run({"prompt": "add tests", "model": "groq", "edit": True})
    assert "-e" in captured[0][2]
    with pytest.raises(ValueError, match="choose one free"):
        app.run({"prompt": "x", "model": "codex", "edit": True})
    with pytest.raises(ValueError, match="choose one free"):
        app.run({"prompt": "x", "edit": True})
