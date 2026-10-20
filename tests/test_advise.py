"""Routing advisor: suggests, never applies."""

import json
from datetime import datetime, timezone

import pytest

from megazword import advise, config
from megazword.cli import main

NOW = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)


def write_runs(cfg, rows):
    cfg.log_path.write_text("\n".join(json.dumps({"time": NOW.isoformat(), **r}) for r in rows)
                            + "\n", encoding="utf-8")


@pytest.fixture
def cfg(tmp_path):
    c = config.Config(log_path=tmp_path / "log.jsonl")
    c.route = {"easy": ["grok", "codex", "claude"], "medium": ["codex", "claude"],
               "hard": ["claude", "codex"]}
    return c


def runs(ai, level, ok, bad, secs=5):
    return ([{"backend": ai, "rating": level, "ok": True, "seconds": secs}] * ok +
            [{"backend": ai, "rating": level, "ok": False, "rejected": "x", "seconds": secs}] * bad)


def test_reorders_when_numbers_say_so(cfg):
    write_runs(cfg, runs("grok", "easy", 1, 4) + runs("codex", "easy", 5, 0))
    easy = advise.advise(cfg, NOW)[0]
    assert easy.changed and easy.suggested[:2] == ["codex", "grok"]
    assert easy.suggested[-1] == "claude"  # unmeasured AI keeps a place
    assert "codex answered 100% of 5 easy runs" in easy.reason


def test_not_enough_data_keeps_current(cfg):
    write_runs(cfg, runs("codex", "medium", 2, 0))
    medium = advise.advise(cfg, NOW)[1]
    assert not medium.changed and "not enough" in medium.reason


def test_votes_tip_the_balance(cfg, monkeypatch):
    write_runs(cfg, runs("claude", "hard", 4, 0) + runs("codex", "hard", 4, 0))
    monkeypatch.setattr(advise, "datetime", type("D", (), {
        "now": staticmethod(lambda tz=None: NOW), "fromisoformat": datetime.fromisoformat}))
    for _ in range(3):
        advise.add_vote("codex", "hard", "design a cache")
    hard = advise.advise(cfg, NOW)[2]
    assert hard.suggested[0] == "codex" and "3 votes" in hard.reason


def test_cli_prints_and_changes_nothing(cfg, capsys):
    write_runs(cfg, runs("grok", "easy", 0, 5) + runs("codex", "easy", 5, 0))
    before = dict(cfg.route)
    assert main(["advise"], {}, cfg) == 0
    out = capsys.readouterr().out
    assert "suggest" in out and "Nothing was changed" in out
    assert cfg.route == before and not (config.HOME / "config.toml").exists()


def test_dashboard_vote_and_advice(tmp_path):
    from megazword.dashboard import App
    from tests.test_cli import FakeBackend
    app = App(config.Config(log_path=tmp_path / "l"), "p", backends={"codex": FakeBackend("codex")})
    assert app.vote({"ai": "codex", "rating": "hard", "prompt": "q"}) == {"ok": True}
    assert advise.read_votes()[0]["ai"] == "codex"
    assert len(app.state()["advice"]) == 3
    with pytest.raises(ValueError):
        app.vote({"ai": "nobody"})
    with pytest.raises(ValueError):
        app.vote({"ai": "codex", "rating": "huge"})
