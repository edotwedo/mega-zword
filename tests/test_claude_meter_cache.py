"""Claude meter cache: shared reading for 2 minutes, last reading on HTTP 429. No network."""

import io
import json
import urllib.error
from datetime import datetime, timedelta, timezone

import pytest

from megazword import usage_sources

DATA = {"five_hour": {"utilization": 40, "resets_at": "2030-01-01T00:00:00Z"},
        "seven_day": {"utilization": 20, "resets_at": "2030-01-05T00:00:00Z"}}


@pytest.fixture
def login(tmp_path, monkeypatch):
    home = tmp_path / "userhome"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / ".credentials.json").write_text(
        json.dumps({"claudeAiOauth": {"accessToken": "fake-token"}}), encoding="utf-8")
    monkeypatch.setattr(usage_sources, "HOME", home)
    monkeypatch.setenv("MEGAZWORD_CLAUDE_METER", "1")  # the meter is opt-in now


def fake_urlopen(calls, error=None):
    def opener(req, timeout):
        calls.append(req.full_url)
        if error:
            raise urllib.error.HTTPError(req.full_url, error, "busy", {}, io.BytesIO(b""))
        return io.BytesIO(json.dumps(DATA).encode())
    return opener


def test_second_read_uses_cache(login, monkeypatch):
    calls = []
    monkeypatch.setattr(usage_sources.urllib.request, "urlopen", fake_urlopen(calls))
    first, second = usage_sources.claude(), usage_sources.claude()
    assert len(calls) == 1
    assert [w.used_percent for w in second.windows] == [w.used_percent for w in first.windows] == [40, 20]
    assert "fake-token" not in usage_sources._claude_cache().read_text(encoding="utf-8")


def test_429_shows_last_reading(login, monkeypatch):
    calls = []
    monkeypatch.setattr(usage_sources.urllib.request, "urlopen", fake_urlopen(calls))
    usage_sources.claude()
    old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    cache = usage_sources._claude_cache()
    cache.write_text(json.dumps({"at": old, "data": DATA}), encoding="utf-8")
    monkeypatch.setattr(usage_sources.urllib.request, "urlopen", fake_urlopen(calls, error=429))
    plan = usage_sources.claude()
    assert len(calls) == 2 and plan.as_of is not None and "429" in plan.note
    assert [w.used_percent for w in plan.windows] == [40, 20]


def test_429_without_cache_still_errors(login, monkeypatch):
    monkeypatch.setattr(usage_sources.urllib.request, "urlopen", fake_urlopen([], error=429))
    with pytest.raises(urllib.error.HTTPError):
        usage_sources.claude()


def test_meter_is_off_by_default_and_never_reads_credentials(monkeypatch, tmp_path):
    """A shipped build must not read Claude credentials or hit the unofficial endpoint."""
    calls = []
    monkeypatch.delenv("MEGAZWORD_CLAUDE_METER", raising=False)
    monkeypatch.setattr(usage_sources, "HOME", tmp_path / "empty")
    monkeypatch.setattr(usage_sources.urllib.request, "urlopen",
                        lambda *a, **k: calls.append(a) or pytest.fail("must not call out"))
    plan = usage_sources.claude()
    assert plan.windows == []
    assert "MEGAZWORD_CLAUDE_METER" in plan.note
    assert calls == []
