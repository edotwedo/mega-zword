"""Compare mode: parallel, no escalation, every run logged."""

import json
import threading
import time
from dataclasses import dataclass

import pytest

from megazword import config
from megazword.cli import main
from tests.test_cli import FakeBackend


@dataclass
class Slow(FakeBackend):
    delay: float = 0.5

    def _run(self, prompt):
        time.sleep(self.delay)
        return super()._run(prompt)


@pytest.fixture
def cfg(tmp_path):
    return config.Config(log_path=tmp_path / "log.jsonl")


@dataclass
class MeetUp(FakeBackend):
    """Answers only once all three AIs are running at the same moment. If
    compare ran them one after another, the barrier would time out."""
    barrier: threading.Barrier = None

    def _run(self, prompt):
        self.barrier.wait(timeout=20)
        return super()._run(prompt)


def test_runs_in_parallel_and_prints_each(cfg, capsys):
    barrier = threading.Barrier(3)
    backends = {n: MeetUp(n, reply=n.upper(), barrier=barrier) for n in "abc"}
    assert main(["run", "hi", "--compare", "a,b,c"], backends, cfg) == 0
    out = capsys.readouterr().out
    for name in "abc":
        assert f"=== {name} · " in out and f"{name.upper()}: " in out
    rows = [json.loads(l) for l in cfg.log_path.read_text().splitlines()]
    assert sorted(r["backend"] for r in rows) == ["a", "b", "c"]
    assert all(r["compare"] and r["forced"] for r in rows)


def test_one_failure_still_shows_the_rest(cfg, capsys):
    backends = {"a": FakeBackend("a", fail=True), "b": FakeBackend("b", reply="B")}
    assert main(["run", "hi", "--compare", "a,b"], backends, cfg) == 0
    out = capsys.readouterr().out
    assert "=== a · failed after" in out and "boom" in out and "B: " in out


def test_all_fail_returns_1(cfg):
    backends = {"a": FakeBackend("a", fail=True), "b": FakeBackend("b", fail=True)}
    assert main(["run", "hi", "--compare", "a,b"], backends, cfg) == 1


@pytest.mark.parametrize("arg,why", [
    ("a", "needs 2 or 3"), ("a,b,c,d", "needs 2 or 3"), ("a,zz", "unknown AI zz"),
    ("a,gone", "not installed"),
])
def test_bad_picks(cfg, capsys, arg, why):
    backends = {n: FakeBackend(n) for n in "abcd"}
    backends["gone"] = FakeBackend("gone", installed=False)
    assert main(["run", "hi", "--compare", arg], backends, cfg) == 2
    assert why in capsys.readouterr().err


def test_not_with_model_or_edit(cfg, capsys):
    backends = {"a": FakeBackend("a"), "b": FakeBackend("b")}
    assert main(["run", "hi", "--compare", "a,b", "-m", "a"], backends, cfg) == 2
    assert main(["run", "hi", "--compare", "a,b", "--edit"], backends, cfg) == 2


def test_dashboard_passes_compare(tmp_path):
    from megazword.dashboard import App
    started = []
    app = App(config.Config(log_path=tmp_path / "l"), "p",
              backends={"a": FakeBackend("a"), "b": FakeBackend("b")},
              launcher=lambda *a: started.append(a) or type("J", (), {"view": lambda s: {}})())
    app.run({"prompt": "hi", "compare": ["a", "b"]})
    assert "--compare" in started[0][2] and "a,b" in started[0][2]
    with pytest.raises(ValueError):
        app.run({"prompt": "hi", "compare": ["a"]})
