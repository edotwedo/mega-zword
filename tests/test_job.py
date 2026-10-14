"""Job planning uses a scripted AI, never a real model or worker."""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from megazword import config, job
from megazword.backends import Backend
from megazword.cli import main
from megazword.pacing import PlanStatus


def piece(title="First", files=None, difficulty="easy", test="python -m pytest -q"):
    return dict(title=title, files=files or ["src/first.py"], difficulty=difficulty, test=test)


@dataclass
class FakePlanner(Backend):
    reply: str = ""
    calls: list[str] = field(default_factory=list)
    fail: bool = False

    def _run(self, prompt):
        self.calls.append(prompt)
        if self.fail:
            raise RuntimeError("fake unavailable")
        return self.reply


def test_cli_plans_prints_and_persists(capsys):
    rows = [piece(), piece("Second", ["src/second.py"], "hard")]
    fake = FakePlanner("fake", reply=json.dumps({"pieces": rows}))
    cfg = config.Config(route={"hard": ["fake"]})
    assert main(["job", "plan", "Add two features"], {"fake": fake}, cfg, statuses=dict) == 0
    assert len(fake.calls) == 1 and "Add two features" in fake.calls[0]
    out = capsys.readouterr()
    assert "First (easy)" in out.out and "Second (hard)" in out.out
    assert "src/second.py" in out.out and "python -m pytest -q" in out.out
    paths = list((config.HOME / "jobs").glob("*/job.json"))
    assert len(paths) == 1
    saved = json.loads(paths[0].read_text(encoding="utf-8"))
    assert saved["pieces"] == rows
    assert saved["id"] == paths[0].parent.name
    assert saved["planner"] == "fake" and saved["status"] == "planned"
    assert saved["job"] == "Add two features"


def test_transitive_overlaps_case_and_normalized_paths():
    rows = [piece("A", ["./src/a.py"]), piece("B", ["src/b.py"], "hard"),
            piece("Independent", ["other.py"]),
            piece("Bridge", ["SRC/A.py", "src/b.py", "src/b.py"], "medium", "pytest tests/test_b.py")]
    result = job.validate_plan({"pieces": rows})["pieces"]
    assert len(result) == 2
    assert result[0]["files"] == ["src/a.py", "src/b.py"]
    assert set(result[0]["title"].split("; ")) == {"A", "B", "Bridge"}
    assert result[0]["difficulty"] == "hard"
    assert result[0]["test"] == "python -m pytest"
    assert result[1] == rows[2]


@pytest.mark.parametrize("data", [
    {}, {"pieces": []}, {"pieces": [piece()] * 33}, {"pieces": [None]},
    {"pieces": [piece(title=" ")]}, {"pieces": [piece(difficulty="extreme")]},
    {"pieces": [dict(piece(), files=[])]}, {"pieces": [dict(piece(), files="a.py")]},
    {"pieces": [dict(piece(), test=None)]}, {"pieces": [piece(test="")]},
    {"pieces": [piece(files=["../outside.py"])]},
    {"pieces": [piece(files=["C:/outside.py"])]},
    {"pieces": [piece(files=["/outside.py"])]},
    {"pieces": [piece(files=[".git/config"])]},
    {"pieces": [piece(files=[".env"])]},
    {"pieces": [piece(files=["src/*.py"])]},
    {"pieces": [piece(files=[123])]},
    {"pieces": [piece(test="pytest; echo unsafe")]},
    {"pieces": [piece(test="python -c 'print(1)'")]},
])
def test_invalid_plans_are_not_saved(data):
    fake = FakePlanner("fake", reply=json.dumps(data))
    with pytest.raises(ValueError):
        job.plan("Some job", fake)
    assert not (config.HOME / "jobs").exists()


@pytest.mark.parametrize("reply,fail", [("not JSON", False), ("", True)])
def test_cli_reports_bad_ai_without_saving(reply, fail, capsys):
    fake = FakePlanner("fake", reply=reply, fail=fail)
    assert main(["job", "plan", "Some job"], {"fake": fake},
                config.Config(route={"hard": ["fake"]}), statuses=dict) == 1
    assert "[megazword]" in capsys.readouterr().err
    assert not (config.HOME / "jobs").exists()


def test_blank_job_does_not_call_ai():
    fake = FakePlanner("fake")
    assert main(["job", "plan", " "], {"fake": fake}, config.Config(), statuses=dict) == 2
    assert fake.calls == []


def test_planner_picks_most_room_and_skips_out(capsys):
    names = ["out", "busy", "spare"]
    fakes = {n: FakePlanner(n, reply=json.dumps([piece()])) for n in names}
    statuses = {n: PlanStatus(n, 0, used, verdict, [])
                for n, used, verdict in [("out", 99, "out"), ("busy", 70, "free"),
                                         ("spare", 20, "free")]}
    assert main(["job", "plan", "Some job"], fakes, config.Config(route={"hard": names}),
                statuses=lambda: statuses) == 0
    assert len(fakes["spare"].calls) == 1
    assert fakes["out"].calls == fakes["busy"].calls == []
    cfg = config.Config(route={"hard": names}, out_until={n: datetime.now(timezone.utc)
                        + timedelta(hours=1) for n in names})
    assert main(["job", "plan", "Some job"], fakes, cfg, statuses=dict) == 1
    assert "no installed AI" in capsys.readouterr().err


def test_multiple_plans_have_distinct_ids_and_accept_json_fence():
    fake = FakePlanner("fake", reply="```json\n" + json.dumps([piece()]) + "\n```")
    first, second = job.plan("First job", fake), job.plan("Second job", fake)
    assert first["id"] != second["id"]
    assert len(list((config.HOME / "jobs").glob("*/job.json"))) == 2


def test_incompatible_overlap_tests_rejected():
    with pytest.raises(ValueError, match="compatible test"):
        job.validate_plan([piece(), piece("Other", test="npm test")])
