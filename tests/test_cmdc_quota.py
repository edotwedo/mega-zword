"""Quota comes from the vendor panel, not spend, and never sends a model task."""
from datetime import datetime, timedelta, timezone
import json
from queue import Queue
import sys
from types import SimpleNamespace

import pytest

from megazword import cmdc_quota, config, usage_sources

NOW = datetime(2026, 10, 20, 19, 0, tzinfo=timezone.utc)
SCREEN = """ USAGE  GOAT Plan · active
███░░░░ 9% used
1,602 requests this month · 30 days to renew
Usage limits
5-hour  ░░░░░░░ 0%
Weekly  ██░░░░░ 18% · resets in 5d 7h
Full breakdown at commandcode.ai/example/settings/usage
Press Esc to close
"""


def test_vendor_windows_are_separate_from_monthly_usage_and_dollars():
    plan = cmdc_quota.parse_screen("\x1b[32m" + SCREEN + "\x1b[0m", NOW)
    assert [(w.name, w.used_percent) for w in plan.windows] == [("5-hour", 0), ("weekly", 18)]
    assert plan.windows[0].resets_at is None  # inactive window, not a guessed reset
    assert plan.windows[1].resets_at == NOW + timedelta(days=5, hours=7)
    assert "monthly 9% used" in plan.note and "GOAT Plan" in plan.note
    assert plan.as_of == NOW and plan.source == "cmdc /usage"
    assert "example" not in plan.note and "requests" not in plan.note


@pytest.mark.parametrize("screen", ["Sign in", "Weekly  18%", SCREEN.replace("18%", "118%")])
def test_partial_or_invalid_panels_never_become_a_zero_quota(screen):
    with pytest.raises(ValueError):
        cmdc_quota.parse_screen(screen, NOW)


def test_last_panel_wins_after_terminal_refresh():
    plan = cmdc_quota.parse_screen(SCREEN + SCREEN.replace("18%", "22%"), NOW)
    assert plan.windows[1].used_percent == 22


def test_cache_is_shared_and_contains_only_quota_fields(monkeypatch):
    calls = []
    monkeypatch.setattr(cmdc_quota, "_command", lambda: ["fake-cli"])
    monkeypatch.setattr(cmdc_quota, "_capture", lambda command: calls.append(command) or SCREEN)
    first = cmdc_quota.read_quota()
    second = cmdc_quota.read_quota()
    assert len(calls) == 1 and first.windows == second.windows
    raw = (config.HOME / "meter_cache_cmdc.json").read_text()
    assert set(json.loads(raw)) == {"as_of", "note", "windows"}
    assert "example" not in raw and "1,602" not in raw and "Press Esc" not in raw


def test_failed_refresh_keeps_reading_age_and_does_not_invent_reset(monkeypatch):
    config.HOME.mkdir(parents=True)
    stamp = NOW - timedelta(minutes=5)
    (config.HOME / "meter_cache_cmdc.json").write_text(json.dumps({
        "as_of": stamp.isoformat(), "note": "GOAT Plan",
        "windows": [{"name": "5-hour", "used_percent": 0, "resets_at": None},
                    {"name": "weekly", "used_percent": 18,
                     "resets_at": (NOW + timedelta(days=5)).isoformat()}],
    }))
    monkeypatch.setattr(cmdc_quota, "_command", lambda: ["fake-cli"])
    def unavailable(command):
        raise TimeoutError("unavailable")
    monkeypatch.setattr(cmdc_quota, "_capture", unavailable)
    result = cmdc_quota.read_quota(NOW)
    assert result.as_of == stamp and result.windows[1].used_percent == 18
    assert "refresh unavailable" in result.note
    assert cmdc_quota.read_quota(NOW + timedelta(days=8)) is None


def test_live_quota_survives_absent_transcripts_and_spend_stays_separate(tmp_path, monkeypatch):
    monkeypatch.setattr(usage_sources, "COMMAND_CODE_ROOT", tmp_path)
    monkeypatch.setattr(cmdc_quota, "read_quota", lambda now=None: cmdc_quota.parse_screen(SCREEN, NOW))
    result = usage_sources.command_code(now=NOW)
    assert result.windows[1].used_percent == 18
    (tmp_path / "session.jsonl").write_text(json.dumps({
        "timestamp": NOW.isoformat(), "usage": {"costUsd": 2.97, "inputTokens": 5000}
    }) + "\n")
    result = usage_sources.command_code(now=NOW)
    assert result.windows[1].used_percent == 18 and "$2.97" in result.note
    assert "not plan credits" in result.note
    assert usage_sources.command_code(tmp_path, NOW).windows == []  # explicit offline mode


@pytest.mark.parametrize("ready", [True, False])
def test_private_terminal_sends_only_fixed_usage_and_always_terminates(monkeypatch, ready):
    class Terminal:
        def __init__(self):
            self.running = True
            self.writes = []
            self.output = Queue()
            self.output.put("Ask \x1b[2myour question...\x1b[0m" if ready else "Sign in to continue")
        def isalive(self):
            return self.running
        def read(self, size):
            value = self.output.get(timeout=4)
            if value is None:
                raise EOFError
            return value
        def write(self, value):
            self.writes.append(value)
            if value == "\r":
                self.output.put(SCREEN)
        def terminate(self, force=False):
            assert force
            self.running = False
            self.output.put(None)
    terminal = Terminal()
    def spawn(command, **kwargs):
        assert command == ["fake"]
        assert "MEGAZWORD_SEAT" not in kwargs["env"]
        return terminal
    monkeypatch.setenv("MEGAZWORD_SEAT", "do-not-register-probe-as-worker")
    monkeypatch.setitem(sys.modules, "winpty", SimpleNamespace(PtyProcess=SimpleNamespace(spawn=spawn)))
    monkeypatch.setattr(cmdc_quota, "TIMEOUT", 4 if ready else .05)
    if ready:
        assert "Weekly" in cmdc_quota._capture(["fake"])
        assert terminal.writes == ["/usage", "\r"]
    else:
        with pytest.raises(TimeoutError):
            cmdc_quota._capture(["fake"])
        assert terminal.writes == []  # never send slash input to a login prompt
    assert not terminal.running
