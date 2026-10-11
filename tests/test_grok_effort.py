"""Grok model + effort follow the task rating. Never calls the real grok CLI."""

from dataclasses import dataclass

from megazword import config
from megazword.backends import (
    Backend, CLIBackend, apply_grok_effort, default_backends, grok_backend, grok_label,
)
from megazword.cli import main
from megazword.rater import Rating


@dataclass
class Fake(Backend):
    reply: str = "ok"

    def _run(self, prompt: str) -> str:
        return self.reply


def test_grok_backend_flags():
    b = grok_backend("grok-4.6", "low")
    assert b.args[-4:] == ["-m", "grok-4.6", "--effort", "low"]
    assert grok_label(b) == "grok (grok-4.6 low)"


def test_default_grok_is_coding_medium():
    g = default_backends()["grok"]
    assert "grok-4.6" in g.args
    assert g.args[g.args.index("--effort") + 1] == "medium"


def test_hard_task_uses_47_high():
    backends = default_backends()
    apply_grok_effort(backends, "hard", config.DEFAULT_GROK)
    g = backends["grok"]
    assert "grok-4.7" in g.args
    assert g.args[g.args.index("--effort") + 1] == "high"


def test_easy_task_uses_46_low():
    backends = default_backends()
    apply_grok_effort(backends, "easy", config.DEFAULT_GROK)
    g = backends["grok"]
    assert "grok-4.6" in g.args
    assert g.args[g.args.index("--effort") + 1] == "low"


def test_fakes_named_grok_are_not_replaced():
    fakes = {"grok": Fake("grok")}
    apply_grok_effort(fakes, "hard", config.DEFAULT_GROK)
    assert isinstance(fakes["grok"], Fake)


def test_config_override(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[grok.hard]\nmodel = "grok-4.6"\neffort = "medium"\n', encoding="utf-8")
    cfg = config.load(path)
    assert cfg.grok["hard"] == ("grok-4.6", "medium")
    assert cfg.grok["easy"] == ("grok-4.6", "low")


def test_run_prints_grok_effort(capsys, tmp_path, monkeypatch):
    monkeypatch.setattr("megazword.cli.plan_statuses", lambda: {})
    cfg = config.Config(
        route={"easy": ["grok"], "medium": ["grok"], "hard": ["grok"]},
        log_path=tmp_path / "log.jsonl",
    )
    # Real CLIBackend would call grok. Use a fake and still print the label
    # by putting a tuned CLIBackend that never runs: we only check the banner
    # for a Fake named grok (untuned). Auto-pick with a real grok_backend is
    # covered above. Here: forced -m grok with a fake stays fake.
    rc = main(["run", "hi", "-m", "grok"], {"grok": Fake("grok")}, cfg,
              rater=lambda p: Rating("medium", "t", "t"))
    assert rc == 0
    err = capsys.readouterr().err
    assert "using grok (you chose it)" in err


def test_cli_tunes_then_uses_label(capsys, tmp_path, monkeypatch):
    made = []

    def fake_gb(model="grok-4.6", effort="medium", edit=False):
        obj = grok_backend(model, effort)
        obj.available = lambda: True  # type: ignore[method-assign]
        obj._run = lambda prompt: "done"  # type: ignore[method-assign]
        made.append((model, effort))
        return obj

    monkeypatch.setattr("megazword.backends.grok_backend", fake_gb)
    cfg = config.Config(
        route={"hard": ["grok"], "medium": ["grok"], "easy": ["grok"]},
        log_path=tmp_path / "log.jsonl",
    )
    backends = {"grok": CLIBackend("grok", exe="grok", args=["-p", "{prompt}"])}
    rc = main(["run", "design a job queue"], backends, cfg,
              rater=lambda p: Rating("hard", "keywords", "rule"),
              statuses=lambda: {})
    assert rc == 0
    assert made == [("grok-4.7", "high")]
    assert "using grok (grok-4.7 high)" in capsys.readouterr().err
