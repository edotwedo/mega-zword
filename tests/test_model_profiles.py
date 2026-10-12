"""Difficulty-specific CLI model settings; all subprocesses stay fake."""

import pytest

from megazword import config
from megazword.backends import (CLIBackend, GeminiBackend, apply_model_profiles,
                                backend_label)
from megazword.cli import main
from megazword.rater import Rating


def test_profiles_default_to_each_cli_defaults(tmp_path):
    cfg = config.load(tmp_path / "missing.toml")
    assert cfg.model_profiles["codex"] == {
        "easy": ("", ""), "medium": ("", ""), "hard": ("", "")}


def test_load_profiles_and_reject_invalid_effort(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[claude.hard]\nmodel = "sonnet"\neffort = "high"\n'
                    '[codex.easy]\neffort = "low"\n', encoding="utf-8")
    cfg = config.load(path)
    assert cfg.model_profiles["claude"]["hard"] == ("sonnet", "high")
    assert cfg.model_profiles["codex"]["easy"] == ("", "low")
    path.write_text('[gemini.medium]\neffort = "maximum"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="effort must be low, medium or high"):
        config.load(path)


def test_set_profile_preserves_config_and_blank_restores_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('rater_model = "local"\n\n[route]\neasy = ["codex"]\n', encoding="utf-8")
    config.set_model_profile("codex", "easy", "gpt-test", "low", path)
    cfg = config.load(path)
    assert cfg.rater_model == "local" and cfg.route["easy"] == ["codex"]
    assert cfg.model_profiles["codex"]["easy"] == ("gpt-test", "low")
    config.set_model_profile("codex", "easy", "", "", path)
    assert config.load(path).model_profiles["codex"]["easy"] == ("", "")


def test_profile_arguments_labels_and_reuse(monkeypatch):
    monkeypatch.setattr("megazword.backends.shutil.which",
                        lambda exe: "agy.exe" if exe == "agy" else None)
    backends = {
        "claude": CLIBackend("claude", exe="claude", args=["-p"]),
        "codex": CLIBackend("codex", exe="codex", args=["exec", "-c", "mcp_servers={}"]),
        "gemini": GeminiBackend("gemini"),
    }
    profiles = {
        "claude": {"easy": ("haiku", "low"), "hard": ("opus", "high")},
        "codex": {"easy": ("gpt-easy", "low")},
        "gemini": {"medium": ("agy-model", "medium")},
    }
    apply_model_profiles(backends, "easy", profiles)
    assert backends["claude"].args[-4:] == ["--model", "haiku", "--effort", "low"]
    assert backends["codex"].args[-4:] == [
        "-c", 'model="gpt-easy"', "-c", 'model_reasoning_effort="low"']
    assert backend_label(backends["codex"]) == "codex (gpt-easy low)"
    apply_model_profiles(backends, "hard", profiles)
    assert backends["claude"].args[-4:] == ["--model", "opus", "--effort", "high"]
    assert backends["codex"].args == ["exec", "-c", "mcp_servers={}"]
    apply_model_profiles(backends, "medium", profiles)
    assert backends["gemini"].args[-4:] == ["--model", "agy-model", "--effort", "medium"]


def test_auto_run_uses_profile_for_rated_task_and_labels_it(tmp_path, capsys):
    backend = CLIBackend("claude", exe="claude", args=["-p"])
    backend.available = lambda: True
    backend._run = lambda prompt: "fake answer"
    cfg = config.Config(
        route={"easy": ["claude"], "medium": ["claude"], "hard": ["claude"]},
        model_profiles={"claude": {"hard": ("opus-test", "high")}},
        log_path=tmp_path / "log.jsonl")
    result = main(["run", "design a reliable queue"], {"claude": backend}, cfg,
                  rater=lambda prompt: Rating("hard", "fake", "fake"), statuses=dict)
    assert result == 0
    assert backend.args[-4:] == ["--model", "opus-test", "--effort", "high"]
    assert "using claude (opus-test high)" in capsys.readouterr().err
