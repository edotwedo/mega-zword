"""Plain `megazword` shows a short start screen."""

import json
import io
import time
from datetime import datetime, timedelta, timezone

from megazword import config, start
from megazword.cli import main
from megazword.usage_sources import PlanUsage, Window

NOW = datetime(2026, 10, 11, 9, tzinfo=timezone.utc)


def cfg_with_runs(tmp_path):
    cfg = config.Config(log_path=tmp_path / "log.jsonl")
    rows = [{"time": (NOW - timedelta(minutes=m)).isoformat(), "backend": b, "ok": ok}
            for m, b, ok in [(90, "grok", True), (30, "codex", False), (5, "claude", True),
                             (2, "claude", True)]]
    cfg.log_path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    cfg.out_until = {"grok": NOW + timedelta(days=6)}
    return cfg


def test_render_contents_and_size(tmp_path):
    meters = [PlanUsage("claude", [Window("5-hour", 62, None), Window("weekly", 10, None),
                                   Window("iguana_necktie", 99, None)], "x"),
              PlanUsage("grok", [], "x")]
    text = start.render(cfg_with_runs(tmp_path), meters, NOW, color=False)
    lines = text.splitlines()
    assert len(lines) < 25 and "\033[" not in text
    assert "claude  [######....]  62% 5-hour" in text  # worst known window, not the credit
    assert "grok    out until" in text  # marked out: no bar, no "no meter"
    assert [l.split()[2] for l in lines if l.startswith("  ") and "ago" in l] == \
        ["claude", "claude", "codex"]  # newest 3 only
    for cmd in ("chat", "dashboard --app", "--compare", "stats", "doctor"):
        assert cmd in text


def test_color_only_on_a_terminal(tmp_path):
    assert "\033[1m" in start.render(config.Config(log_path=tmp_path / "l"), [], NOW, color=True)


def test_slow_meters_dont_block(tmp_path):
    def slow():
        time.sleep(10)
        return []
    t0 = time.monotonic()
    assert start._meters(slow, wait=0.3) is None
    assert time.monotonic() - t0 < 2
    text = start.render(config.Config(log_path=tmp_path / "l"), None and [], NOW, color=False)
    assert "Plans" in text


def test_bare_megazword_shows_it(capsys, monkeypatch):
    monkeypatch.setattr(start, "_meters", lambda *a, **k: None)
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "meters still loading" in out and "megazword --help" in out


def test_bare_megazword_opens_detached_app_on_terminal(monkeypatch):
    class Terminal(io.StringIO):
        def isatty(self):
            return True
    terminal = Terminal()
    opened = []
    monkeypatch.setattr("sys.stdout", terminal)
    monkeypatch.setattr("megazword.cli._launch_dashboard_app", lambda: opened.append(True))
    assert main([], cfg=config.Config()) == 0
    assert opened == [True]
    assert terminal.getvalue() == "Started Mega Zword app. Run `megazword start` for the text screen.\n"


def test_no_app_env_and_explicit_start_keep_text_screen(monkeypatch):
    class Terminal(io.StringIO):
        def isatty(self):
            return True
    monkeypatch.setattr(start, "_meters", lambda *a, **k: [])
    terminal = Terminal()
    monkeypatch.setattr("sys.stdout", terminal)
    monkeypatch.setenv("MEGAZWORD_NO_APP", "1")
    assert main([], cfg=config.Config()) == 0
    assert "Try:" in terminal.getvalue()
    terminal.seek(0)
    terminal.truncate(0)
    monkeypatch.delenv("MEGAZWORD_NO_APP")
    assert main(["start"], cfg=config.Config()) == 0
    assert "Try:" in terminal.getvalue()


def test_dashboard_app_launch_is_detached_and_never_uses_a_shell(monkeypatch):
    import subprocess
    from megazword import cli

    launched = []
    cli._launch_dashboard_app(lambda command, **options: launched.append((command, options)))
    command, options = launched[0]
    assert command[-3:] == ["megazword", "dashboard", "--app"]
    assert options["stdin"] is options["stdout"] is options["stderr"] is subprocess.DEVNULL
    assert options["close_fds"] and "shell" not in options
    if cli.os.name == "nt":
        assert options["creationflags"] == (subprocess.DETACHED_PROCESS |
                                             subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
        assert options["start_new_session"]


def test_long_notes_fit_80_columns_without_cutting_words(tmp_path):
    import re
    from textwrap import shorten
    from megazword.meters import summarize

    note = "No CLI usage meter available; Mega Zword recorded 0 runs in the last 24 hours"
    meters = [PlanUsage(name, [], "x", note=note)
              for name in ("claude", "codex", "grok", "gemini", "groq", "openrouter")]
    summary = summarize(meters[3], {}, NOW).line()
    assert summary == f"gemini  {shorten(note, width=60, placeholder='...')}"
    for color in (False, True):
        text = start.render(cfg_with_runs(tmp_path), meters, NOW, color=color)
        lines = re.sub(r"\x1b\[[0-9;]*m", "", text).splitlines()
        assert len(lines) < 25
        assert all(len(line) <= 80 for line in lines)
        assert "gemini" in text and "..." in text


def test_extra_plans_do_not_overflow_start_screen(tmp_path):
    meters = [PlanUsage(f"ai{i}", [], "x", note="no meter") for i in range(10)]
    text = start.render(cfg_with_runs(tmp_path), meters, NOW, color=False)
    assert len(text.splitlines()) < 25
    assert "more plans: megazword usage" in text
