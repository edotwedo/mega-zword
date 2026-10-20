"""Reserve floors only annotate usage output; meter data and routing stay intact."""

import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from megazword import cli, config, usage_sources
from megazword.meters import summarize_all
from megazword.usage_sources import PlanUsage, Window


@pytest.mark.parametrize("settings, expected", [
    (None, {}),
    ("[usage.reserve]\nclaude = 35\ncodex = 12.5", {"claude": 35, "codex": 12.5}),
    ("[usage.reserve]\nclaude = -4\ncodex = 150", {"claude": 0, "codex": 100}),
    ('[usage.reserve]\nclaude = "bad"\ncodex = true\ngrok = nan', {}),
    ("usage = false", {}),
    ("[usage]\nreserve = false", {}),
])
def test_usage_reserve_config(tmp_path, settings, expected):
    path = tmp_path / "config.toml"
    if settings is not None:
        path.write_text(settings, encoding="utf-8")
    assert config.load(path).usage_reserve == expected


@pytest.mark.parametrize("settings, used, suffix", [
    ("", 64, "reserve 20%, 16% spendable"),
    ("[usage.reserve]\nclaude = 30", 64, "reserve 30%, 6% spendable"),
    ("[usage.reserve]\ncodex = 30", 64, "reserve 20%, 16% spendable"),
    ("", 80, "reserve 20%, AT RESERVE: hold heavy work"),
    ("", 90, "reserve 20%, AT RESERVE: hold heavy work"),
    ("[usage.reserve]\nclaude = 40", 64, "reserve 40%, AT RESERVE: hold heavy work"),
    ("[usage.reserve]\nclaude = -5", 64, "reserve 0%, 36% spendable"),
    ("[usage.reserve]\nclaude = 150", 64, "reserve 100%, AT RESERVE: hold heavy work"),
])
def test_usage_reserve_suffix(monkeypatch, capsys, settings, used, suffix):
    config.HOME.mkdir(parents=True)
    (config.HOME / "config.toml").write_text(settings, encoding="utf-8")
    plans = [PlanUsage("claude", [Window("5-hour", used, None),
                                  Window("weekly", 10, None)], "fake"),
             PlanUsage("codex", [Window("weekly", 50, None)], "fake")]
    monkeypatch.setattr(usage_sources, "all_usage", lambda *args: plans)
    assert cli.show_usage() == 0
    output = capsys.readouterr().out
    summaries = summarize_all(plans, {})
    assert output.splitlines()[0] == summaries[0].line() + f"  ({suffix})"
    assert "reserve" in output.splitlines()[2]  # weekly-only AI gets its floor too

    # Strip only the new suffixes and compare every other byte against the old
    # show_usage path, including window details, budget, and run-total rows.
    originals = [SimpleNamespace(service=s.service, state="none", line=s.line)
                 for s in summaries]
    monkeypatch.setattr("megazword.meters.summarize_all", lambda *args: originals)
    assert cli.show_usage() == 0
    assert re.sub(r"  \(reserve [^\n]+\)", "", output) == capsys.readouterr().out


def test_usage_unknown_and_out_unchanged(monkeypatch, capsys):
    plans = [PlanUsage("claude", [], "fake", note="no reading"),
             PlanUsage("codex", [Window("mystery", 64, None)], "fake"),
             PlanUsage("grok", [Window("weekly", 64, None)], "fake")]
    until = datetime.now(timezone.utc) + timedelta(days=1)
    monkeypatch.setattr(config, "load", lambda: config.Config(out_until={"grok": until}))
    monkeypatch.setattr(usage_sources, "all_usage", lambda *args: plans)
    assert cli.show_usage() == 0
    output = capsys.readouterr().out
    assert "reserve" not in output
    for summary in summarize_all(plans, {"grok": until}):
        assert summary.line() in output.splitlines()
