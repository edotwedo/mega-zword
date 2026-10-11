"""Tests use fake backends and a fake rater so they never spend paid usage."""

import json
from dataclasses import dataclass

import pytest

from megazword import config
from megazword.backends import Backend, CLIBackend
from megazword.cli import main
from megazword.rater import Rating, rule_rate


@dataclass
class FakeBackend(Backend):
    reply: str = "hello"
    fail: bool = False
    installed: bool = True

    def available(self) -> bool:
        return self.installed

    def _run(self, prompt: str) -> str:
        if self.fail:
            raise RuntimeError("boom")
        return f"{self.reply}: {prompt}"


@pytest.fixture
def cfg(tmp_path):
    return config.Config(
        route={"easy": ["cheap"], "medium": ["cheap"], "hard": ["gone", "strong"]},
        log_path=tmp_path / "log.jsonl",
    )


def fakes(**kw):
    return {"fake": FakeBackend("fake", **kw)}


def rated(level):
    return lambda prompt: Rating(level, "test", "fake")


def test_forced_model_prints_answer(capsys, cfg):
    assert main(["run", "hi there", "-m", "fake"], fakes(), cfg) == 0
    out = capsys.readouterr()
    assert out.out.strip() == "hello: hi there"
    assert "using fake" in out.err


def test_unknown_model(capsys, cfg):
    assert main(["run", "hi", "-m", "nope"], fakes(), cfg) == 2
    assert "Choose from: fake" in capsys.readouterr().err


def test_failure_is_reported_not_raised(capsys, cfg):
    assert main(["run", "hi", "-m", "fake"], fakes(fail=True), cfg) == 1
    assert "boom" in capsys.readouterr().err


def test_auto_pick_skips_missing_and_logs(capsys, cfg):
    backends = {
        "cheap": FakeBackend("cheap", reply="c"),
        "gone": FakeBackend("gone", installed=False),
        "strong": FakeBackend("strong", reply="s"),
    }
    assert main(["run", "design a system"], backends, cfg, rated("hard")) == 0
    out = capsys.readouterr()
    assert out.out.strip() == "s: design a system"
    assert "rated hard" in out.err and "using strong" in out.err
    entry = json.loads(cfg.log_path.read_text().splitlines()[-1])
    assert entry["backend"] == "strong" and entry["rating"] == "hard" and entry["ok"]


def test_auto_pick_with_nothing_installed(capsys, cfg):
    assert main(["run", "hi"], {}, cfg, rated("easy")) == 1
    assert "no installed AI" in capsys.readouterr().err


def test_backends_lists_availability(capsys, cfg):
    missing = CLIBackend("ghost", exe="definitely-not-a-real-cli-xyz")
    assert main(["backends"], {"ghost": missing}, cfg) == 0
    out = capsys.readouterr().out
    assert "ghost" in out and "not found" in out


def test_prompt_placeholder_goes_in_args():
    b = CLIBackend("x", exe="python", args=["-c", "{prompt}"])
    cmd, stdin = b._command("print(1)")
    assert cmd[-1] == "print(1)" and stdin is None


def test_prompt_goes_to_stdin_without_placeholder():
    b = CLIBackend("x", exe="python", args=["-"])
    cmd, stdin = b._command("print(1)")
    assert stdin == "print(1)" and "print(1)" not in cmd


@pytest.mark.parametrize("prompt,level", [
    ("what's 2+2", "easy"),
    ("refactor the auth module", "hard"),
    ("x" * 500, "medium"),
])
def test_rule_rater(prompt, level):
    assert rule_rate(prompt).level == level


def test_rule_raises_low_local_rating(monkeypatch):
    from megazword import rater
    monkeypatch.setattr(rater.ollama, "generate",
                        lambda *a, **k: '{"rating": "medium", "reason": "meh"}')
    assert rater.rate("design a job queue").level == "hard"
    assert rater.rate("explain lists").level == "medium"


def test_rater_falls_back_when_ollama_down(monkeypatch):
    from megazword import rater

    def down(*a, **k):
        raise OSError("refused")
    monkeypatch.setattr(rater.ollama, "generate", down)
    r = rater.rate("hi")
    assert r.source == "rule" and "unavailable" in r.reason


def test_codex_usage_from_log(tmp_path, monkeypatch):
    from megazword import usage_sources
    day = tmp_path / ".codex" / "sessions" / "2026" / "10" / "10"
    day.mkdir(parents=True)
    rec = {"payload": {"rate_limits": {
        "primary": {"used_percent": 3.0, "window_minutes": 300, "resets_at": 1791711582},
        "secondary": {"used_percent": 0.0, "window_minutes": 10080, "resets_at": 1792298382}}}}
    (day / "rollout.jsonl").write_text(json.dumps(rec) + "\n")
    monkeypatch.setattr(usage_sources, "HOME", tmp_path)
    plan = usage_sources.codex()
    assert [(w.name, w.used_percent) for w in plan.windows] == [("5-hour", 3.0), ("weekly", 0.0)]
