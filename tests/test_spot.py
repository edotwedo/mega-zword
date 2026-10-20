"""Fake meters only: no AI calls, no network."""
from types import SimpleNamespace

from megazword import spot


def usage(service, used, name="weekly"):
    return SimpleNamespace(service=service,
                           windows=[SimpleNamespace(name=name, used_percent=used)])


def test_only_the_tight_plans_warn():
    lines = spot.warnings([usage("grok", 72), usage("claude", 78), usage("codex", 40)])
    assert lines == ["claude: 22% left - HAND OFF SOON"]


def test_floor_is_a_stop():
    assert spot.warnings([usage("claude", 85)]) == ["claude: 15% left - STOP (at floor)"]


def test_remaining_uses_the_tightest_recognized_window():
    meter = SimpleNamespace(service="gemini",
                            windows=[SimpleNamespace(name="5-hour", used_percent=10),
                                     SimpleNamespace(name="weekly", used_percent=81)])
    assert spot.remaining(meter) == 19


def test_unknown_buckets_never_block():
    meter = SimpleNamespace(service="claude",
                            windows=[SimpleNamespace(name="weekly", used_percent=65),
                                     SimpleNamespace(name="iguana_necktie", used_percent=100)])
    assert spot.remaining(meter) == 35
    assert spot.warnings([meter]) == []


def test_command_writes_a_handoff_note(tmp_path, monkeypatch):
    import megazword.usage_sources as sources
    monkeypatch.setattr(spot.config, "HOME", tmp_path)
    monkeypatch.setattr(sources, "all_usage", lambda *a, **k: [usage("claude", 80)])
    out = []
    assert spot.command(write=out.append) == 0
    assert "claude: 20% left - STOP (at floor)" in out
    assert (tmp_path / "spot-handoff.json").exists()
