"""The andon cord: one switch stops every agent job before its next step.

The point of these tests is that pulling it costs nothing and throws nothing
away: no step is spent after it goes up, and edits already made stay on disk.
"""

import json

import pytest

from megazword import agent, andon


def flag(tmp_path):
    return tmp_path / "ANDON"


def call(name, **args):
    return {"tool_calls": [{"id": "c1", "type": "function", "function": {
        "name": name, "arguments": json.dumps(args)}}]}


def backend(replies, after=None):
    from megazword.free_apis import OpenAICompatibleBackend

    class Scripted2(OpenAICompatibleBackend):
        def __init__(self):
            super().__init__("groq")
            self.replies = iter(replies)
            self.calls = 0

        def available(self):
            return True

        def chat(self, messages, tools=None, timeout=None):
            self.calls += 1
            reply = next(self.replies)
            if after is not None:
                after()
            return reply

    return Scripted2()


@pytest.fixture(autouse=True)
def pace_free(monkeypatch):
    monkeypatch.setattr(agent, "DEFAULT_PACE", dict.fromkeys(agent.DEFAULT_PACE, 0))


# --- the switch itself ------------------------------------------------------


def test_pull_release_and_state_line(tmp_path, monkeypatch):
    monkeypatch.setattr(andon, "flag_path", lambda: flag(tmp_path))
    assert andon.status_line() == "andon off: jobs run"
    andon.pull("smoke in the room")
    assert andon.is_on()
    assert "smoke in the room" in andon.status_line()
    assert andon.release() is True
    assert not andon.is_on()
    assert andon.release() is False          # already off, and it says so


def test_command_output(tmp_path, monkeypatch):
    monkeypatch.setattr(andon, "flag_path", lambda: flag(tmp_path))
    said = []
    assert andon.command("on", write=said.append) == 0
    assert said[-1].startswith("andon ON")
    assert andon.command("off", write=said.append) == 0
    assert said[-1] == "andon released: jobs run again"
    andon.command("off", write=said.append)
    assert said[-1] == "andon was already off"
    andon.command(None, write=said.append)
    assert said[-1] == "andon off: jobs run"


def test_flag_without_a_reason_reads_cleanly(tmp_path, monkeypatch):
    monkeypatch.setattr(andon, "flag_path", lambda: flag(tmp_path))
    andon.pull()
    assert andon.status_line() == "andon ON: jobs stop before their next step"
    assert "edits remain in the work folder" in andon.stop_message()


# --- the loop obeys it ------------------------------------------------------


def test_a_pulled_andon_costs_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(andon, "flag_path", lambda: flag(tmp_path))
    model = backend([call("write_file", path="a.py", text="should not happen")])
    loop = agent.wrap(model, {"root": tmp_path}, None)
    andon.pull("stopping the line")
    with pytest.raises(RuntimeError, match="andon is pulled"):
        loop._run("do the work")
    assert model.calls == 0                       # not one step was spent
    assert not (tmp_path / "a.py").exists()


def test_pulled_mid_job_stops_at_the_next_step_and_keeps_edits(tmp_path, monkeypatch):
    monkeypatch.setattr(andon, "flag_path", lambda: flag(tmp_path))
    model = backend([call("write_file", path="a.py", text="work so far")],
                    after=lambda: andon.pull("pulled while it ran"))
    loop = agent.wrap(model, {"root": tmp_path}, None)
    with pytest.raises(RuntimeError, match="andon is pulled"):
        loop._run("keep working")
    assert model.calls == 1                       # the second step was not taken
    assert (tmp_path / "a.py").read_text() == "work so far"   # nothing rolled back
