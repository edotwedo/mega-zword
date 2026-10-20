"""B12: per-task model and effort for Claude, Codex and Gemini."""

from megazword import config
from megazword.backends import (CLIBackend, CodexBackend, GeminiBackend, apply_levels,
                                default_backends, grok_label)
from megazword.cli import main


def _levels(**tables):
    levels = {"claude": {}, "codex": {}, "gemini": {}}
    levels.update(tables)
    return levels


def test_config_reads_levels(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[claude.hard]\nmodel = "opus"\neffort = "high"\n'
                    '[codex.easy]\neffort = "low"\n[gemini.bogus]\nmodel = "x"\n', encoding="utf-8")
    cfg = config.load(path)
    assert cfg.levels["claude"] == {"hard": ("opus", "high")}
    assert cfg.levels["codex"] == {"easy": ("", "low")}
    assert cfg.levels["gemini"] == {}


def test_unset_level_keeps_cli_defaults():
    backends = default_backends(free_models={})
    before = {n: list(b.args) for n, b in backends.items() if isinstance(b, CLIBackend)}
    apply_levels(backends, "hard", config.DEFAULT_GROK, _levels())
    assert backends["claude"].args == before["claude"]
    assert backends["codex"].args == before["codex"]


def test_levels_add_the_documented_flags():
    backends = default_backends(free_models={})
    original = backends["codex"]
    apply_levels(backends, "hard", config.DEFAULT_GROK, _levels(
        claude={"hard": ("opus", "high")}, codex={"hard": ("gpt-5.5", "xhigh")},
        gemini={"hard": ("gemini-3.1-pro-high", "")}))
    claude, codex, gemini = backends["claude"], backends["codex"], backends["gemini"]
    assert claude.args[-4:] == ["--model", "opus", "--effort", "high"]
    assert isinstance(codex, CodexBackend) and codex is not original
    assert codex.args[-4:] == ["-m", "gpt-5.5", "-c", "model_reasoning_effort=xhigh"]
    assert "-m" not in original.args  # the shared object isn't changed
    assert isinstance(gemini, GeminiBackend) and gemini.level_args == ["--model", "gemini-3.1-pro-high"]
    assert grok_label(claude) == "claude (opus high)"
    assert grok_label(codex) == "codex (gpt-5.5 xhigh)"
    assert grok_label(gemini) == "gemini (gemini-3.1-pro-high)"


def test_agy_level_args_go_before_the_prompt(monkeypatch):
    monkeypatch.setattr("megazword.backends.shutil.which", lambda exe: exe if exe == "agy" else None)
    g = GeminiBackend("gemini", level_args=["--model", "m1", "--effort", "low"])
    g._pick()
    assert g.args[-2:] == ["-p", "{prompt}"]
    assert g.args[0] == "--dangerously-skip-permissions" and "--model" in g.args and "--effort" in g.args


def test_fakes_are_left_alone():
    from dataclasses import dataclass
    from megazword.backends import Backend

    @dataclass
    class Fake(Backend):
        def _run(self, prompt):
            return "ok"

    fakes = {"claude": Fake("claude")}
    apply_levels(fakes, "hard", config.DEFAULT_GROK, _levels(claude={"hard": ("opus", "high")}))
    assert isinstance(fakes["claude"], Fake)


def test_doctor_lists_levels(tmp_path):
    from megazword import doctor
    (tmp_path / "config.toml").write_text(
        '[claude.hard]\nmodel = "opus"\neffort = "high"\n[codex.easy]\neffort = "turbo"\n',
        encoding="utf-8")
    line = next(c for c in doctor.checks(tmp_path) if c.name == "model levels")
    assert "claude.hard opus/high" in line.detail and line.level == "WARN"
