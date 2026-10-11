"""Plain `megazword` shows a short start screen."""

import json
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
    assert "grok    no meter" in text and "grok until" in text
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
