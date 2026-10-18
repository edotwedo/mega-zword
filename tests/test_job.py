"""megazword job plan: fake AI only, no network."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

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


TWO = json.dumps([
    {"title": "lock tests", "files": ["tests/test_filelock.py"], "difficulty": "easy",
     "test": "pytest tests/test_filelock.py"},
    {"title": "lock impl", "files": ["src/megazword/filelock.py"], "difficulty": "medium",
     "test": "pytest tests/test_filelock.py"},
])

OVERLAP = json.dumps([
    {"title": "a", "files": ["src/megazword/job.py"], "difficulty": "easy", "test": "pytest tests/test_job.py"},
    {"title": "b", "files": ["src/megazword/job.py", "src/megazword/cli.py"], "difficulty": "hard",
     "test": "pytest tests/test_cli.py"},
])


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(job.config, "HOME", tmp_path)
    return tmp_path


def test_parse_and_merge_overlapping_files():
    pieces = job.parse_pieces(OVERLAP)
    assert len(pieces) == 1
    assert pieces[0].difficulty == "hard"
    assert pieces[0].files == ("src/megazword/cli.py", "src/megazword/job.py")
    assert "a; b" == pieces[0].title


def test_parse_strips_fences_and_rejects_parent_paths():
    fenced = "```json\n" + TWO + "\n```"
    assert len(job.parse_pieces(fenced)) == 2
    with pytest.raises(ValueError):
        job.parse_pieces('[{"title": "x", "files": ["../secret"], "difficulty": "easy", "test": ""}]')


def test_plan_saves_job_json(isolated_home, capsys):
    backends = {"grok": FakeAI("grok", reply=TWO)}
    assert job.plan_job("add lock tests", backends, home=isolated_home, job_id="t1") == 0
    out = capsys.readouterr().out
    assert "job t1  2 pieces" in out
    payload = json.loads((isolated_home / "jobs" / "t1" / "job.json").read_text(encoding="utf-8"))
    assert payload["planner"] == "grok"
    assert payload["text"] == "add lock tests"
    assert len(payload["pieces"]) == 2
    assert "Split this coding job" in backends["grok"].last


def test_plan_bad_json_is_one_line(isolated_home, capsys):
    assert job.plan_job("x", {"grok": FakeAI("grok", reply="nope")}) == 1
    assert "bad plan" in capsys.readouterr().out


def test_cli_job_plan_uses_fake(isolated_home, capsys):
    cfg = config.Config(log_path=isolated_home / "log.jsonl")
    backends = {"codex": FakeAI("codex", reply=TWO)}
    assert main(["job", "plan", "split this"], backends=backends, cfg=cfg) == 0
    out = capsys.readouterr().out
    assert "2 pieces" in out and "lock tests" in out


def test_parse_plan_reads_brief_and_old_bare_lists():
    rows = '[{"title": "a", "files": ["a.py"], "difficulty": "easy", "test": ""}]'
    brief, pieces = job.parse_plan('```json\n{"brief": "  Goal:   add a.  ", "pieces": ' + rows + "}\n```")
    assert brief == "Goal: add a." and [p.title for p in pieces] == ["a"]
    assert job.parse_plan(rows)[0] == "" and len(job.parse_pieces(rows)) == 1
    assert len(job.parse_plan('{"brief": "' + "x" * 5000 + '", "pieces": ' + rows + "}")[0]) == job.BRIEF_CHARS
    with pytest.raises(ValueError):
        job.parse_plan('{"brief": "no pieces"}')


def test_plan_saves_brief(isolated_home, capsys):
    reply = '{"brief": "Shared goal.", "pieces": ' + TWO + "}"
    backends = {"grok": FakeAI("grok", reply=reply)}
    assert job.plan_job("x", backends, home=isolated_home, job_id="t2") == 0
    payload = json.loads((isolated_home / "jobs" / "t2" / "job.json").read_text(encoding="utf-8"))
    assert payload["brief"] == "Shared goal." and len(payload["pieces"]) == 2
    assert '"brief"' in backends["grok"].last
