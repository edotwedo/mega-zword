"""Sentinel collector: fake events only; no admin, no real Windows log."""

import json

from megazword import config, sentinel
from megazword.cli import main


EVENTS = {
    "System": [
        {"time": "2026-10-11T08:00:00+00:00", "id": 6005, "provider": "EventLog",
         "record_id": 10, "message": "The Event log service was started."},
        {"time": "2026-10-11T07:55:00+00:00", "id": 1074, "provider": "User32",
         "record_id": 9, "message": "phil initiated a restart."},
    ],
    "Security": [
        {"time": "2026-10-11T08:01:00+00:00", "id": 4624, "provider": "Security",
         "record_id": 44, "message": "An account was successfully logged on."},
    ],
    "Microsoft-Windows-NetworkProfile/Operational": [
        {"time": "2026-10-11T08:02:00+00:00", "id": 10000, "provider": "NetworkProfile",
         "record_id": 3, "message": "Network connected."},
        {"time": "2026-10-11T08:03:00+00:00", "id": 10001, "provider": "NetworkProfile",
         "record_id": 4, "message": "Network disconnected."},
    ],
}


def fake_reader(channel, ids, since):
    out = []
    for raw in EVENTS.get(channel, []):
        rec = sentinel._record(raw, channel)
        if rec and rec["event_id"] in ids and sentinel._newer(rec, since):
            out.append(rec)
    out.sort(key=lambda r: (r["time"], r["record_id"]))
    return out


def test_collect_writes_jsonl_and_is_idempotent():
    added = sentinel.collect(fake_reader)
    assert {e["kind"] for e in added} >= {"boot", "login", "network_up", "network_down"}
    rows = sentinel.recent(20)
    assert len(rows) == 5
    assert rows[0]["kind"] == "network_down"  # newest first
    assert sentinel.path().exists()
    again = sentinel.collect(fake_reader)
    assert again == []
    assert len(sentinel.recent(20)) == 5


def test_status_and_log_text():
    sentinel.collect(fake_reader)
    text = sentinel.format_status()
    assert "last boot" in text and "boot" in text
    assert "security log" in text and "readable" in text
    log_text = sentinel.format_log(3)
    assert "network_down" in log_text and "10001" in log_text


def test_security_access_denied_is_noted():
    def reader(channel, ids, since):
        if channel == "Security":
            raise OSError("Access is denied")
        return fake_reader(channel, ids, since)
    sentinel.collect(reader)
    s = sentinel.summary()
    assert s["security_readable"] is False
    assert s["last_login"] is None
    assert "Event Log Readers" in sentinel.format_status()


def test_cli_log_and_status(capsys, monkeypatch):
    assert main(["sentinel", "log"]) == 0
    assert "no sentinel events" in capsys.readouterr().out
    sentinel.collect(fake_reader)
    monkeypatch.setattr(sentinel, "collect", lambda reader=None: [])
    assert main(["sentinel", "log", "-n", "2"]) == 0
    out = capsys.readouterr().out
    assert "network" in out
    assert main(["sentinel", "status"]) == 0
    assert "Sentinel" in capsys.readouterr().out


def test_unknown_event_id_skipped():
    assert sentinel._record({"time": "t", "id": 1, "record_id": 1}, "System") is None


def test_powershell_reader_parses_one_object(monkeypatch):
    payload = json.dumps({"time": "2026-10-11T08:00:00.0000000Z", "id": 6005,
                          "provider": "EventLog", "record_id": 1,
                          "message": "started"})
    monkeypatch.setattr(sentinel, "_powershell", lambda script: payload)
    rows = sentinel.windows_reader("System", (6005, 6006), None)
    assert len(rows) == 1 and rows[0]["kind"] == "boot"


def test_dashboard_state_includes_sentinel(tmp_path, monkeypatch):
    from megazword import dashboard
    from megazword.usage_sources import PlanUsage, Window
    from datetime import datetime, timedelta, timezone
    monkeypatch.setattr(config, "HOME", tmp_path)
    sentinel.collect(fake_reader)
    log = tmp_path / "log.jsonl"
    log.write_text("{}\n")
    usage = dashboard.Usage(lambda: [PlanUsage("claude", [Window("5-hour", 1.0,
        datetime.now(timezone.utc) + timedelta(hours=1))], "test")])
    app = dashboard.App(config.Config(log_path=log), "proj", usage, {}, lambda *a: None)
    s = app.state()
    assert s["sentinel"]["last_boot"]["kind"] == "boot"
    assert s["sentinel"]["recent"]
