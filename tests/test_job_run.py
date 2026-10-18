"""Tests for megazword job run command (step 1 of team engine)."""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from dataclasses import dataclass

from megazword import config, job
from megazword.backends import Backend
from megazword.cli import main


@dataclass
class FakeAI(Backend):
    reply: str = "[]"
    fail: bool = False
    installed: bool = True

    def available(self) -> bool:
        return self.installed

    def _run(self, prompt: str) -> str:
        self.last = prompt
        if self.fail:
            raise RuntimeError("boom")
        return self.reply


TEST_PLAN = {
    "id": "test-job-001",
    "text": "Add a simple feature",
    "planner": "grok",
    "pieces": [
        {
            "title": "simple piece",
            "files": ["src/megazword/test_example.py"],
            "difficulty": "easy",
            "test": "echo hello",
        }
    ],
}


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(job.config, "HOME", tmp_path)
    return tmp_path


def _write_job(home, job_id, plan):
    p = home / "jobs" / job_id
    p.mkdir(parents=True, exist_ok=True)
    (p / "job.json").write_text(json.dumps(plan), encoding="utf-8")
    return p


def test_command_run_missing_job(isolated_home, capsys):
    backends = {"grok": FakeAI()}
    cfg = config.Config(log_path=isolated_home / "log.jsonl")
    result = main(["job", "run", "no-such-job"], backends=backends, cfg=cfg)
    assert result == 1
    assert "no job" in capsys.readouterr().out.lower()


def test_command_run_no_pieces(isolated_home, capsys):
    _write_job(isolated_home, "empty-job", {
        "id": "empty-job", "text": "Empty plan", "planner": "grok", "pieces": [],
    })
    backends = {"grok": FakeAI()}
    cfg = config.Config(log_path=isolated_home / "log.jsonl")
    result = main(["job", "run", "empty-job"], backends=backends, cfg=cfg)
    assert result == 1


def test_command_run_prints_piece_line(isolated_home, monkeypatch, capsys):
    _write_job(isolated_home, "t1", TEST_PLAN)

    calls = []

    def fake_run_pieces(plan, repo, job_id=None, workers=2, **kwargs):
        calls.append((plan, repo, job_id, workers))
        return {
            "runner_status": "complete",
            "results": [
                {
                    "index": 1, "title": "simple piece", "status": "passed",
                    "ai": "groq-llama-3.1", "branch": "", "commit": "", "tests": "",
                    "reason": "", "seconds": 1.0, "requests": 0, "est_tokens": 0, "tried": [],
                }
            ],
        }

    import megazword.job as job_module
    monkeypatch.setattr(job_module.job_workers, "run_pieces", fake_run_pieces)

    backends = {"grok": FakeAI()}
    cfg = config.Config(log_path=isolated_home / "log.jsonl")
    result = main(["job", "run", "t1", "--workers", "3"], backends=backends, cfg=cfg)
    assert result == 0
    out = capsys.readouterr().out
    assert "1. simple piece  passed  groq-llama-3.1" in out
    assert calls[0][2] == "t1" and calls[0][3] == 3
