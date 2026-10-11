"""`megazword out` edits only the [out] line it's asked to."""

from datetime import datetime, timedelta, timezone

import pytest

from megazword import config
from megazword.cli import main

NOW = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)

ORIGINAL = """# my comment
rater_model = "qwen2.5:1.5b"

[out]
# keep this comment
codex = 2026-10-12

[route]
easy = ["grok"]
"""


def test_parse_until_relative_and_absolute():
    assert config.parse_until("7d", NOW) == NOW + timedelta(days=7)
    assert config.parse_until("5h", NOW) == NOW + timedelta(hours=5)
    assert config.parse_until("2026-10-17T23:30").hour == 23
    with pytest.raises(ValueError):
        config.parse_until("next tuesday")


def test_set_replace_add_remove_keeps_everything_else(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(ORIGINAL, encoding="utf-8")
    config.set_out(p, "grok", NOW + timedelta(days=1))
    config.set_out(p, "codex", NOW + timedelta(days=2))
    text = p.read_text(encoding="utf-8")
    assert "# my comment" in text and "# keep this comment" in text
    assert text.index("grok = ") < text.index("[route]")  # stays inside [out]
    assert text.count("codex = ") == 1
    cfg = config.load(p)
    assert set(cfg.out_until) == {"grok", "codex"} and cfg.route["easy"] == ["grok"]
    config.set_out(p, "codex", None)
    assert set(config.load(p).out_until) == {"grok"}


def test_creates_out_table_when_missing(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[route]\neasy = ["grok"]\n', encoding="utf-8")
    config.set_out(p, "grok", NOW)
    assert "grok" in config.load(p).out_until and config.load(p).route["easy"] == ["grok"]
    config.set_out(p, "nobody", None)  # removing a missing mark is a no-op


def test_rejects_bad_names(tmp_path):
    with pytest.raises(ValueError):
        config.set_out(tmp_path / "c.toml", "grok = 1\n[x]", NOW)


def test_cli_out_flow(capsys):
    assert main(["out", "grok", "--until", "3d"], {}) == 0
    assert "marked out until" in capsys.readouterr().out
    assert main(["out"], {}) == 0
    assert "grok" in capsys.readouterr().out
    assert main(["out", "grok", "--clear"], {}) == 0
    assert main(["out"], {}) == 0
    assert "no AI is marked out" in capsys.readouterr().out
    assert main(["out", "grok"], {}) == 2
    assert main(["out", "grok", "--until", "someday"], {}) == 2


def test_dashboard_out_toggle():
    from megazword.dashboard import App
    from tests.test_cli import FakeBackend
    app = App(config.load(), "p", backends={"grok": FakeBackend("grok")})
    assert app.set_out({"ai": "grok", "until": "2d"}) == {"ok": True}
    assert "grok" in app.state()["out"]
    app.set_out({"ai": "grok", "clear": True})
    assert "grok" not in app.state()["out"]
    with pytest.raises(ValueError):
        app.set_out({"ai": "nobody"})
