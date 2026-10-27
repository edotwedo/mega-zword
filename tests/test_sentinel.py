"""Sentinel collector and alerts: fake events/HTTP only; no admin, no real ntfy."""

import json
import subprocess

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


def test_two_failures_alert_then_recovery():
    cfg = config.Config(sentinel_urls=["https://ex.test/a"], ntfy_topic="mz-test",
                        healthchecks_url="https://hc.test/ping")
    calls = []
    down = {"https://ex.test/a"}

    def getter(url, data=None, headers=None):
        calls.append((url, data is not None))
        if data is not None:
            return 200
        if url in down:
            raise OSError("down")
        return 200

    first = sentinel.check_sites(cfg, getter)
    assert first["alerts"] == []
    second = sentinel.check_sites(cfg, getter)
    assert any("down: https://ex.test/a" in a for a in second["alerts"])
    assert ("https://ntfy.sh/mz-test", True) in calls
    assert ("https://hc.test/ping", False) in calls
    down.clear()
    third = sentinel.check_sites(cfg, getter)
    assert any("back up: https://ex.test/a" in a for a in third["alerts"])
    assert sum(1 for u, posted in calls if u.startswith("https://ntfy.sh/") and posted) == 2


def test_single_failure_does_not_alert():
    cfg = config.Config(sentinel_urls=["https://ex.test/b"], ntfy_topic="mz-test")
    ntfy = []

    def getter(url, data=None, headers=None):
        if data is not None:
            ntfy.append(url)
            return 200
        raise OSError("down")

    sentinel.check_sites(cfg, getter)
    assert ntfy == []


def test_install_dry_run_does_not_create_task(capsys, monkeypatch):
    monkeypatch.setattr(sentinel, "_is_windows", lambda: True)
    ran = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: ran.append(a) or type(
        "R", (), {"returncode": 0, "stderr": "", "stdout": ""})())
    assert sentinel.install(False) == 0
    assert ran == []
    out = capsys.readouterr().out
    assert "install --yes" in out and "ntfy" in out


def test_install_yes_on_unix_skips_schtasks(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(sentinel, "_is_windows", lambda: False)
    ran = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: ran.append(a) or type(
        "R", (), {"returncode": 0, "stderr": "", "stdout": ""})())
    assert sentinel.install(True) == 0
    assert [a[0][0] for a in ran] == ["systemctl", "systemctl"]
    assert "OnUnitActiveSec=5min" in (tmp_path / "systemd/user/megazword-sentinel.timer").read_text()
    assert "sentinel check" in (tmp_path / "systemd/user/megazword-sentinel.service").read_text()


def test_install_yes_creates_tasks(monkeypatch, capsys):
    monkeypatch.setattr(sentinel, "_is_windows", lambda: True)
    ran = []

    class R:
        returncode = 0
        stderr = ""
        stdout = "ok"

    monkeypatch.setattr(subprocess, "run", lambda args, **k: ran.append(args) or R())
    assert sentinel.install(True) == 0
    names = [args[args.index("/TN") + 1] for args in ran]
    assert names == ["MegaZword-Sentinel", "MegaZword-Sentinel-Logon"]
    assert "ntfy topic" in capsys.readouterr().out
    loaded = config.load()
    assert loaded.ntfy_topic.startswith("mz-")


def test_task_runs_windowless_python(monkeypatch, capsys):
    monkeypatch.setattr(sentinel, "_is_windows", lambda: True)
    monkeypatch.setattr("megazword.desktop.launcher_python", lambda: r"C:\py\pythonw.exe")
    ran = []

    class R:
        returncode, stderr, stdout = 0, "", "ok"

    monkeypatch.setattr(subprocess, "run", lambda args, **k: ran.append(args) or R())
    assert sentinel.install(True) == 0
    assert all(args[args.index("/TR") + 1].startswith('"C:\\py\\pythonw.exe" -m megazword.cli')
               for args in ran)


def test_powershell_timeout_and_garbage_become_oserror(monkeypatch):
    import pytest
    monkeypatch.setattr(sentinel, "_is_windows", lambda: True)

    def slow(*a, **k):
        raise subprocess.TimeoutExpired("powershell", 30)

    monkeypatch.setattr(subprocess, "run", slow)
    with pytest.raises(OSError, match="over 30s"):
        sentinel._powershell("x")
    monkeypatch.setattr(sentinel, "_powershell", lambda script: "WARNING: not json")
    with pytest.raises(OSError, match="unreadable System"):
        sentinel.windows_reader("System", (6005,), None)


def test_sentinel_command_survives_a_broken_reader(monkeypatch, capsys):
    def broken(reader=None):
        raise OSError("unreadable System event log output")

    monkeypatch.setattr(sentinel, "collect", broken)
    assert main(["sentinel", "status"]) == 0
    assert "collect skipped" in capsys.readouterr().err


def test_damaged_cursor_does_not_stop_collection():
    event = {"time": "2026-10-12T10:00:00Z", "record_id": 5}
    assert sentinel._newer(event, {"time": "2026-10-12T10:00:00Z", "record_id": "oops"})
    assert not sentinel._newer(event, {"time": "2026-10-12T11:00:00Z", "record_id": 1})
