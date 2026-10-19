"""Restart-window limits use scripted models and injected time, with no network."""
import pytest

from megazword import agent, room
from megazword.run_control import Control
from test_agent import Scripted, call, coding


@pytest.fixture(autouse=True)
def isolated_calls(monkeypatch):
    monkeypatch.setattr(agent, "DEFAULT_PACE", dict.fromkeys(agent.DEFAULT_PACE, 0))
    posts = []
    monkeypatch.setattr(room, "say", lambda *args, **kwargs: posts.append((args, kwargs)))
    return posts


def spread_replies():
    return [call("read_file", path="missing-1"), call("read_file", path="source.txt"),
            call("read_file", path="missing-2"), call("list_files", glob="*"),
            call("read_file", path="missing-3"), call("finish", summary="done")]


@pytest.mark.parametrize("times,stopped", [([0, 300, 600], True),
                                          ([0, 660, 1320], False),
                                          ([0, 601, 700], False)])
def test_spread_failures_use_sliding_window(tmp_path, isolated_calls, times, stopped):
    (tmp_path / "source.txt").write_text("PRIVATE FILE TEXT")
    control = Control(tmp_path / "run-controls" / "job-123")
    loop, model = coding(tmp_path, spread_replies(), max_steps=20,
                         clock=iter(times).__next__, control=control)
    result = loop.run("inspect source")
    assert result.ok is not stopped
    assert loop.request_count == (5 if stopped else 6)
    assert loop.request_count < loop.max_steps
    events = control.view()["events"]
    if stopped:
        assert "stopped after 3 failures in 10 min" in result.error
        assert sum(e["phase"] == "stopped: 3 failures in 10 min" for e in events) == 1
        assert len(isolated_calls) == 1
        args, kwargs = isolated_calls[0]
        assert args == ("hive", "job-123: stopped after 3 failures in 10 min; shelved, see job log. @phil")
        assert "PRIVATE FILE TEXT" not in str(isolated_calls)
        assert (tmp_path / "source.txt").read_text() == "PRIVATE FILE TEXT"
    else:
        assert not isolated_calls
        assert not any(e["phase"].startswith("stopped:") for e in events)


def test_window_counts_failovers_and_tool_failures_together(tmp_path, isolated_calls):
    loop, first = coding(tmp_path, [call("read_file", path="missing"), RuntimeError("offline")],
                         max_steps=20, clock=lambda: 0, job_id="job-mixed")
    second = Scripted([RuntimeError("offline too")])
    second.name = "second"
    third = Scripted([call("finish", summary="never reached")])
    third.name = "third"
    loop.fallback_backends = [second, third]
    result = loop.run("job")
    assert not result.ok and "3 failures in 10 min" in result.error
    assert len(first.seen) == 2 and len(second.seen) == 1 and not third.seen
    assert len(isolated_calls) == 1
    assert isolated_calls[0][0][1].startswith("job-mixed:")


def test_room_failure_preserves_stop_and_edits(tmp_path, monkeypatch, isolated_calls):
    attempts = []

    def broken_say(*args, **kwargs):
        attempts.append(args)
        raise OSError("room unavailable")

    monkeypatch.setattr(room, "say", broken_say)
    replies = [call("write_file", path="draft.txt", text="PRIVATE DRAFT")]
    replies += [call("read_file", path=f"missing-{i}") for i in range(5)]
    loop, model = coding(tmp_path, replies, max_steps=20, clock=lambda: 0, job_id="job-draft")
    result = loop.run("make a draft")
    assert not result.ok and "3 failures in 10 min" in result.error
    assert len(model.seen) == 4
    assert (tmp_path / "draft.txt").read_text() == "PRIVATE DRAFT"
    assert len(attempts) == 1 and "PRIVATE DRAFT" not in str(attempts)


def test_window_counts_each_tool_in_a_batch(tmp_path, isolated_calls):
    batch = {"tool_calls": [call("read_file", path=f"missing-{i}")["tool_calls"][0]
                            for i in range(4)]}
    loop, model = coding(tmp_path, [batch], clock=lambda: 0)
    result = loop.run("inspect files")
    assert not result.ok and "3 failures in 10 min" in result.error
    assert len(model.seen) == 1 and len(isolated_calls) == 1
