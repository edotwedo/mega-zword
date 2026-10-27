"""Offline regression tests for the local Night Shift driver."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def night_local(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts" / "night_local.py"
    spec = importlib.util.spec_from_file_location("night_local", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name, value in {
        "REPO": tmp_path,
        "JOBS": tmp_path / "jobs.json",
        "STATE": tmp_path / "state.json",
        "LOG": tmp_path / "local.log",
        "STOP": tmp_path / "STOP",
    }.items():
        monkeypatch.setattr(module, name, value)

    def unexpected_process(args, **kwargs):
        pytest.fail(f"Unexpected subprocess: {args}")

    monkeypatch.setattr(module.subprocess, "run", unexpected_process)
    return module


@pytest.fixture
def branch_calls(night_local, monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        assert args[:4] == ["git", "rev-parse", "--verify", "--quiet"] or (
            args[:2] == ["git", "checkout"]
        ), f"Unexpected subprocess: {args}"
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(night_local.subprocess, "run", fake_run)
    return calls


def test_stop_short_circuits_without_running_backend(night_local):
    night_local.STOP.touch()
    night_local.JOBS.write_text(
        json.dumps({"jobs": [{"id": "pending", "prompt": "Do work"}]}),
        encoding="utf-8",
    )

    assert night_local.main() == 0
    assert "stopped: STOP file is set" in night_local.LOG.read_text()
    assert not night_local.STATE.exists()


def test_clear_queue_exits_zero(night_local, branch_calls):
    night_local.JOBS.write_text(json.dumps({"jobs": []}), encoding="utf-8")

    assert night_local.main() == 0
    assert branch_calls == []  # one branch now: the driver never switches branches
    assert "queue clear: no local jobs" in night_local.LOG.read_text()
    assert not night_local.STATE.exists()


def test_already_done_job_is_skipped(night_local, branch_calls):
    night_local.JOBS.write_text(
        json.dumps({"jobs": [{"id": "finished", "prompt": "Do work"}]}),
        encoding="utf-8",
    )
    state = json.dumps({"finished": {"state": "done", "backend": "codex"}})
    night_local.STATE.write_text(state, encoding="utf-8")

    assert night_local.main() == 0
    assert branch_calls == []  # one branch now: the driver never switches branches
    assert night_local.STATE.read_text(encoding="utf-8") == state
    assert "queue clear: every local job is done or failed" in night_local.LOG.read_text()


def test_tree_digest_detects_content_change_with_identical_status(night_local, monkeypatch):
    tracked = night_local.REPO / "tracked.txt"
    calls = []

    def fake_run(args, **kwargs):
        assert kwargs == {"cwd": night_local.REPO, "capture_output": True, "text": True}
        calls.append(args)
        if args == ["git", "diff", "HEAD"]:
            # Model a tracked file already modified relative to HEAD.
            stdout = "-original\n+" + tracked.read_text(encoding="utf-8")
        else:
            assert args == ["git", "status", "--porcelain"]
            stdout = " M tracked.txt\n"
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(night_local.subprocess, "run", fake_run)
    tracked.write_text("first edit\n", encoding="utf-8")
    before = night_local.tree_digest()
    assert night_local.tree_digest() == before
    tracked.write_text("second edit\n", encoding="utf-8")

    assert night_local.tree_digest() != before
    assert calls == [["git", "diff", "HEAD"], ["git", "status", "--porcelain"]] * 3
