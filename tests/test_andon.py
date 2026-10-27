"""Andon uses local state and scripted jobs; no network or real models."""
import json
from datetime import datetime

import pytest

from megazword import agent, andon, config, room
from megazword.cli import main
from megazword.run_control import Control
from test_agent import call, coding


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(agent, "DEFAULT_PACE", dict.fromkeys(agent.DEFAULT_PACE, 0))
    posts = []
    monkeypatch.setattr(room, "say", lambda *args, **kwargs: posts.append((args, kwargs)))
    return posts


def test_cli_round_trip(capsys, monkeypatch, isolated):
    monkeypatch.setenv("MEGAZWORD_SEAT", "Andon-test")
    assert main(["andon"]) == 0
    assert "andon off" in capsys.readouterr().out
    assert main(["andon", "on", "inspect", "the draft"]) == 0
    data = json.loads((config.HOME / "ANDON").read_text(encoding="utf-8"))
    assert data["reason"] == "inspect the draft"
    assert data["who"] == "Andon-test"
    assert datetime.fromisoformat(data["time"]).utcoffset().total_seconds() == 0
    assert "andon ON" in capsys.readouterr().out
    assert main(["andon"]) == 0
    assert "inspect the draft" in capsys.readouterr().out
    assert main(["andon", "off"]) == 0
    assert not andon.is_on()
    assert "andon off" in capsys.readouterr().out
    assert main(["andon", "off"]) == 0
    assert [args[1] for args, _ in isolated] == [
        "Andon-test: ANDON on - inspect the draft. All jobs pause at their next step.",
        "Andon-test: ANDON off", "Andon-test: ANDON off"]


def test_no_reason_unknown_seat_and_atomic_write(monkeypatch):
    writes = []
    original = andon.write_atomic

    def capture(path, text):
        writes.append((path, text))
        original(path, text)

    monkeypatch.setattr(andon, "write_atomic", capture)
    assert main(["andon", "on"]) == 0
    assert len(writes) == 1 and writes[0][0] == config.HOME / "ANDON"
    assert andon.details()["who"] == "unknown"
    assert andon.details()["reason"] == ""


def test_room_failure_does_not_block_switch(monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("offline")

    monkeypatch.setattr(room, "say", broken)
    assert main(["andon", "on", "review"]) == 0
    assert andon.is_on()
    assert main(["andon", "off"]) == 0
    assert not andon.is_on()


def test_mid_job_pause_keeps_edits_and_does_not_count_failure(tmp_path, monkeypatch, isolated):
    control = Control(tmp_path / "run-controls" / "job-andon")
    ticks = []
    loop, model = coding(tmp_path, [call("read_file", path="missing-1"),
                                   call("read_file", path="missing-2"),
                                   call("write_file", path="draft.txt", text="work so far")],
                         control=control, clock=lambda: ticks.append(0) or 0)
    original = model.chat

    def chat(*args, **kwargs):
        reply = original(*args, **kwargs)
        if len(model.seen) == 3:
            andon.pull("inspect draft")
        return reply

    monkeypatch.setattr(model, "chat", chat)
    result = loop.run("edit the draft")
    assert not result.ok
    assert result.error == ("paused by andon: inspect draft; edits remain in the work folder; "
                            "run `megazword andon off` and re-run")
    assert len(model.seen) == 3
    assert (tmp_path / "draft.txt").read_text() == "work so far"
    assert len(ticks) == 2  # Only the two tool failures entered the restart window.
    phases = [event["phase"] for event in control.view()["events"]]
    assert phases[-1] == "paused: andon (inspect draft)"
    assert "failed" not in phases
    assert not any(phase.startswith("stopped:") for phase in phases)
    assert not isolated  # No failure-window escalation.


def test_flag_on_before_start_uses_no_model_steps(tmp_path):
    andon.pull("hold")
    loop, model = coding(tmp_path, [])
    result = loop.run("work")
    assert not result.ok and "paused by andon: hold" in result.error
    assert not model.seen


def test_off_runs_normally_with_one_flag_check_per_step(tmp_path, monkeypatch):
    andon.pull("old pause")
    andon.release()
    path = andon.flag_path()
    original = type(path).exists
    stats = []

    def exists(self, *args, **kwargs):
        if self == path:
            stats.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(type(path), "exists", exists)
    loop, model = coding(tmp_path, [call("list_files", glob="*"), call("finish", summary="done")])
    result = loop.run("inspect folder")
    assert result.ok and result.text == "done"
    assert len(model.seen) == len(stats) == 2
