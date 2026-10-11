import json
from datetime import datetime, timedelta, timezone

import pytest

from megazword import answers, config, memory
from megazword.cli import COMMAND_GROUPS, build_parser, main
from megazword.export import cutoff, render


NOW = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)


def seed(tmp_path):
    mem = memory.Memory(config.HOME, "demo")
    old = (NOW - timedelta(days=20)).isoformat()
    edge = (NOW - timedelta(days=7)).isoformat()
    for kind, text, stamp in [
        ("decision", "old decision", old), ("note", "old note", old),
        ("done", "old done", old), ("note", "boundary note", edge),
        ("done", "finished work", NOW.isoformat()),
        ("note", "future note", (NOW + timedelta(seconds=1)).isoformat()),
    ]:
        mem.add(kind, text, by="phil", time=stamp)
    rows = [dict(time=t, project=p, backend="codex", prompt=prompt, answer=answer)
            for t, p, prompt, answer in [
                (old, "demo", "old prompt", "old answer"),
                (edge, "demo", "# Heading\n\n## Sneaky\n<script>x</script>", "code\n```\n`````\nend"),
                (NOW.isoformat(), "other", "other prompt", "other answer"),
                ("broken", "demo", "broken prompt", "broken answer"),
                ((NOW + timedelta(seconds=1)).isoformat(), "demo", "future prompt", "future answer"),
            ]]
    answers.path().write_text("\n".join(map(json.dumps, rows)), encoding="utf-8")
    path = tmp_path / "runs.jsonl"
    runs = [dict(time=t, project=p, backend=b, ok=ok, seconds=2, est_tokens=10)
            for t, p, b, ok in [
                (edge, "demo", "codex", True),
                (NOW.isoformat(), "demo", "codex", False),
                (old, "demo", "oldai", True),
                (NOW.isoformat(), "other", "otherai", True),
                (NOW.isoformat(), None, "legacyai", True),
                ((NOW + timedelta(seconds=1)).isoformat(), "demo", "futureai", True),
            ]]
    path.write_text("\n".join(map(json.dumps, runs)), encoding="utf-8")
    return config.Config(log_path=path)


def test_content_window_and_project_scope(tmp_path):
    cfg = seed(tmp_path)
    text = render("demo", cfg.log_path, now=NOW)
    for wanted in ["old decision", "boundary note", "finished work", "AI: codex", "## Past answers",
                   "| codex | 2 | 1 | 0 | 1 | 4.0 | 20 |"]:
        assert wanted in text
    for absent in ["old note", "old done", "old prompt", "other prompt", "broken prompt",
                   "future prompt", "future note", "otherai", "oldai", "legacyai", "futureai"]:
        assert absent not in text
    dated = render("demo", cfg.log_path, "2026-10-11", NOW)
    assert "boundary note" not in dated and "finished work" in dated
    assert "old decision" in dated


def test_markdown_escaping(tmp_path):
    cfg = seed(tmp_path)
    text = render("demo", cfg.log_path, now=NOW)
    assert "> \\# Heading\n> \n> \\#\\# Sneaky" in text
    assert "<script>" not in text
    assert "\n``````\ncode\n```\n`````\nend\n``````\n" in text
    assert "\n# Heading" not in text and "\n## Sneaky" not in text


def test_cli_stdout_file_and_overwrite(tmp_path, capsys):
    cfg = seed(tmp_path)
    args = ["export", "-p", "demo", "--since", "2026-01-01"]
    assert main(args, {}, cfg) == 0
    assert capsys.readouterr().out.startswith("# Project report: demo")
    target = tmp_path / "report.md"
    assert main([*args, "--out", str(target)], {}, cfg) == 0
    assert capsys.readouterr().out == ""
    target.write_text("keep me", encoding="utf-8")
    assert main([*args, "--out", str(target)], {}, cfg) == 1
    assert "--force" in capsys.readouterr().err
    assert target.read_text() == "keep me"
    assert main([*args, "--out", str(target), "--force"], {}, cfg) == 0
    assert "## Decisions" in target.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["../escape", "..", "a/b", "a\\b", "C:foo", "", "x" * 65, "missing"])
def test_invalid_project(name, tmp_path, capsys):
    target = tmp_path / "not-created.md"
    assert main(["export", "-p", name, "--out", str(target)], {}, config.Config()) == 2
    assert not target.exists()
    assert "project" in capsys.readouterr().err


@pytest.mark.parametrize("value", ["0d", "-1d", "tomorrow", "2026-02-30", "2027-01-01", "9" * 100 + "d"])
def test_invalid_since(value):
    with pytest.raises(ValueError, match="--since"):
        cutoff(value, NOW)


def test_date_and_relative_boundaries():
    assert cutoff("7d", NOW) == NOW - timedelta(days=7)
    assert cutoff("2026-10-11", NOW) == NOW.replace(hour=0)


def test_empty_default_project(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(memory, "project_name", lambda: "empty")
    assert main(["export"], {}, config.Config(log_path=tmp_path / "missing")) == 0
    text = capsys.readouterr().out
    assert "Project report: empty" in text and "No runs in this window" in text
    assert "export" in COMMAND_GROUPS["See"]
    assert "export project memory" in build_parser().format_help()


def test_no_config_or_api_keys_exported(tmp_path, monkeypatch):
    cfg = seed(tmp_path)
    monkeypatch.setenv("CUSTOM_API_KEY", "private-env-value")
    mem = memory.Memory(config.HOME, "demo")
    mem.add("decision", "private-env-value sk-abcdefghijklmnop api_key=private-inline-value")
    (config.HOME / "config.toml").write_text('secret = "private-config-value"', encoding="utf-8")
    text = render("demo", cfg.log_path, now=NOW)
    for secret in ["private-env-value", "sk-abcdefghijklmnop", "private-inline-value", "private-config-value"]:
        assert secret not in text
    assert "REDACTED" in text


def test_all_retained_answers_not_just_twenty(tmp_path):
    cfg = seed(tmp_path)
    rows = [dict(time=NOW.isoformat(), project="demo", backend="codex", prompt=f"prompt {i}", answer="ok")
            for i in range(70)]
    answers.path().write_text("\n".join(map(json.dumps, rows)), encoding="utf-8")
    assert render("demo", cfg.log_path, now=NOW).count("AI: codex") == 70
