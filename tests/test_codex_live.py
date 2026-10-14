"""Live Codex meter through a fake `codex app-server`: no real Codex, no network."""

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from megazword import usage_sources

FAKE = str(Path(__file__).with_name("fake_codex_app_server.py"))


def test_live_meter_reads_app_server(monkeypatch):
    monkeypatch.setattr(usage_sources, "_codex_cmd", lambda: [sys.executable, FAKE])
    checked_after = datetime.now(timezone.utc)
    plan = usage_sources.codex()
    assert plan.source == "codex app-server (live)"
    assert checked_after <= plan.as_of <= datetime.now(timezone.utc)
    by_name = {w.name: w for w in plan.windows}
    assert by_name["5-hour"].used_percent == 10 and by_name["weekly"].used_percent == 29
    assert by_name["weekly"].resets_at.timestamp() == 1900500000


def test_silent_app_server_times_out_and_falls_back(monkeypatch):
    monkeypatch.setattr(usage_sources, "_codex_cmd", lambda: [sys.executable, FAKE, "silent"])
    start = time.monotonic()
    assert usage_sources.codex_live(timeout=2) is None
    assert time.monotonic() - start < 15
    monkeypatch.setattr(usage_sources, "codex_live", lambda: None)
    assert usage_sources.codex().source == "codex session log"  # the old fallback
