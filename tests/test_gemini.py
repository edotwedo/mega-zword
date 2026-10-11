"""Gemini integration without installing it, logging in, or spending usage."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from megazword import backends, cli, config, doctor, ollama, usage_sources
from tests.test_doctor import fake_external


def test_missing_gemini_is_harmless(monkeypatch):
    monkeypatch.setattr(backends.shutil, "which", lambda name: None)
    backend = backends.default_backends(free_models=config.Config().free)["gemini"]
    assert isinstance(backend, backends.CLIBackend)
    assert not backend.available()
    result = backend.run("hello")
    assert not result.ok and "not installed or not on PATH" in result.error


@pytest.mark.parametrize("returncode", [0, 42])
def test_gemini_pipes_long_prompt_and_reports_errors(monkeypatch, returncode):
    prompt = 'private "quoted" & | %PATH% $value\n' + "x" * 50_000
    # Old Gemini CLI only (no agy installed).
    monkeypatch.setattr(backends.shutil, "which",
                        lambda name: None if name == "agy" else "fake-gemini.cmd")
    calls = []

    class Process:
        def __init__(self, cmd, **kwargs):
            calls.append(cmd)
            assert kwargs["stdin"] == backends.subprocess.PIPE
            assert kwargs["encoding"] == "utf-8"
            self.returncode = returncode

        def communicate(self, stdin, timeout):
            assert stdin == prompt
            assert timeout == 19
            return "  fake answer\n", "unsupported approval mode" if returncode else ""

    monkeypatch.setattr(backends.subprocess, "Popen", Process)
    backend = backends.default_backends(free_models=config.Config().free)["gemini"]
    assert backend.available()
    backend.timeout = 19
    result = backend.run(prompt)
    assert calls == [["fake-gemini.cmd", "--approval-mode", "plan", "--output-format", "text"]]
    assert result.backend == "gemini"
    assert result.ok == (returncode == 0)
    if returncode:
        assert "exited with code 42" in result.error
        assert "unsupported approval mode" in result.error
    else:
        assert result.text == "fake answer"


def test_gemini_edit_is_excluded_and_explained(capsys):
    assert "gemini" not in backends.default_backends(edit=True, free_models={})
    assert cli.main(["run", "write a file", "--edit", "-m", "gemini"],
                    cfg=config.Config()) == 2
    assert "Gemini edit mode is disabled" in capsys.readouterr().err


@pytest.mark.parametrize("installed", [False, True])
def test_init_discovers_gemini_without_adding_routes(monkeypatch, capsys, installed):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(backends.shutil, "which", lambda name:
                        "fake-gemini.cmd" if installed and name == "gemini" else None)
    monkeypatch.setattr(ollama, "reachable", lambda: False)
    assert cli.main(["init"], cfg=config.Config()) == 0
    output = capsys.readouterr().out
    assert f"installed AIs: {'gemini' if installed else 'none'}" in output
    assert all("gemini" not in route for route in config.Config().route.values())
    assert all("gemini" not in route for route in
               config.load(config.HOME / "config.toml").route.values())


@pytest.mark.parametrize("installed", [False, True])
def test_doctor_checks_gemini_and_accepts_custom_route(tmp_path, monkeypatch, installed):
    fake_external(monkeypatch)
    monkeypatch.setattr(doctor.shutil, "which", lambda name:
                        f"/fake/{name}" if installed and name != "agy" else None)
    commands = []

    def version(cmd, **kwargs):
        commands.append(cmd)
        return SimpleNamespace(returncode=0, stdout="fake 1.0\n", stderr="")

    monkeypatch.setattr(doctor.subprocess, "run", version)
    monkeypatch.setattr("megazword.backends.run_quick", version)  # doctor's hang-proof runner
    (tmp_path / "config.toml").write_text('[route]\neasy = ["gemini"]\n')
    lines = "\n".join(item.line() for item in doctor.checks(tmp_path))
    assert ("OK gemini: fake 1.0" if installed else "WARN gemini: not on PATH") in lines
    assert (["/fake/gemini", "--version"] in commands) == installed
    assert "OK routes: known backends only" in lines
    assert "gemini 600s" in lines


def test_gemini_meter_counts_only_own_runs(tmp_path, monkeypatch, capsys):
    now = datetime.now(timezone.utc)
    rows = [
        {"time": (now - timedelta(hours=1)).isoformat(), "backend": "gemini", "ok": True},
        {"time": (now - timedelta(days=2)).isoformat(), "backend": "gemini", "ok": False},
        {"time": (now - timedelta(days=8)).isoformat(), "backend": "gemini", "ok": True},
        {"time": now.isoformat(), "backend": "grok", "ok": True},
    ]
    monkeypatch.setattr(config, "HOME", tmp_path)
    path = tmp_path / "log.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\ninvalid json\n")
    meter = usage_sources.gemini()
    assert meter.service == "gemini" and meter.windows == []
    assert meter.source == "Mega Zword run log"
    assert "not tracked yet" in meter.note
    assert "1 runs in the last 5h, 2 this week" in meter.note
    monkeypatch.setattr(usage_sources, "SOURCES", {})
    assert next(p for p in usage_sources.all_usage(path) if p.service == "gemini") == meter
    assert cli.show_usage() == 0
    output = capsys.readouterr().out
    assert "gemini  plan usage not tracked yet" in output
    assert any(line.split()[:3] == ["gemini", "1", "1"] for line in output.splitlines())


def test_gemini_meter_without_log(tmp_path):
    meter = usage_sources.gemini(tmp_path / "missing.jsonl")
    assert meter.windows == []
    assert "0 runs in the last 5h, 0 this week" in meter.note


def test_gemini_meter_failure_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(usage_sources, "SOURCES", {})

    def broken(path):
        raise OSError("fake unreadable log")

    monkeypatch.setattr(usage_sources, "gemini", broken)
    meter = next(p for p in usage_sources.all_usage(tmp_path / "log.jsonl")
                 if p.service == "gemini")
    assert meter.source == "error" and "fake unreadable log" in meter.note


def test_gemini_prefers_antigravity_cli(monkeypatch):
    # Google retired the Gemini CLI for personal accounts; agy replaces it.
    monkeypatch.setattr(backends.shutil, "which", lambda name: f"fake-{name}.exe")
    calls = []

    class Process:
        def __init__(self, cmd, **kwargs):
            calls.append(cmd)
            self.returncode = 0

        def communicate(self, stdin, timeout):
            assert stdin == "hello"
            return "hi\n", ""

    monkeypatch.setattr(backends.subprocess, "Popen", Process)
    backend = backends.default_backends(free_models=config.Config().free)["gemini"]
    result = backend.run("hello")
    assert calls == [["fake-agy.exe", "-p", "--mode", "plan", "--output-format", "text",
                      "--disable-slash-commands"]]
    assert result.ok and result.text == "hi" and result.backend == "gemini"
    assert "gemini" not in backends.default_backends(edit=True, free_models={})


def test_doctor_finds_antigravity_cli(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which",
                        lambda name: "fake-agy.exe" if name == "agy" else None)
    monkeypatch.setattr(backends, "run_quick", lambda cmd, timeout: SimpleNamespace(
        returncode=0, stdout="1.3.3\n", stderr=""))
    check = next(c for c in doctor.checks() if c.name == "gemini")
    assert check.level == "OK" and "1.3.3" in check.detail


AGY_USAGE = {"status": "SUCCESS", "command": {"name": "usage", "data": {"groups": [
    {"name": "Gemini Models", "buckets": [
        {"id": "gemini-5h", "window": "5h", "remaining_fraction": 0.75,
         "reset_time": "2026-10-12T03:00:00Z"},
        {"id": "gemini-weekly", "window": "weekly", "remaining_fraction": 0.4,
         "reset_time": "2026-10-15T00:00:00Z"}]},
    {"name": "Claude and GPT models", "buckets": [
        {"id": "other-5h", "window": "5h", "remaining_fraction": 0.0,
         "reset_time": "2026-10-12T03:00:00Z"}]},
]}}}


def test_gemini_meter_reads_agy_usage(monkeypatch):
    monkeypatch.setattr(usage_sources, "_agy_path", lambda: "fake-agy.exe")
    seen = []

    def fake_run(cmd, timeout):
        seen.append(cmd)
        return SimpleNamespace(returncode=0, stdout=json.dumps(AGY_USAGE), stderr="")

    monkeypatch.setattr(backends, "run_quick", fake_run)
    meter = usage_sources.gemini()
    assert seen == [["fake-agy.exe", "-p", "/usage", "--output-format", "json"]]
    assert meter.source == "agy /usage"
    by_name = {w.name: w for w in meter.windows}
    assert by_name["5-hour"].used_percent == pytest.approx(25)
    assert by_name["weekly"].used_percent == pytest.approx(60)
    assert by_name["weekly"].resets_at == datetime(2026, 10, 15, tzinfo=timezone.utc)
    # Antigravity's Claude/GPT pool is shown but never drives the Gemini meter.
    from megazword import meters, pacing
    summary = meters.summarize(meter, {})
    assert summary.state == "meter" and summary.used == pytest.approx(60)
    assert pacing.status(meter).max_used_percent == pytest.approx(60)


def test_gemini_meter_agy_failure_is_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(usage_sources, "SOURCES", {})
    monkeypatch.setattr(usage_sources, "_agy_path", lambda: "fake-agy.exe")
    monkeypatch.setattr(backends, "run_quick", lambda cmd, timeout: SimpleNamespace(
        returncode=1, stdout="", stderr="not signed in"))
    meter = next(p for p in usage_sources.all_usage(tmp_path / "log.jsonl")
                 if p.service == "gemini")
    assert meter.source == "error" and "not signed in" in meter.note


def test_parse_agy_usage_tolerates_odd_shapes():
    assert usage_sources.parse_agy_usage({}) == []
    assert usage_sources.parse_agy_usage({"command": {"data": {"groups": [
        "junk", {"name": "Gemini Models", "buckets": [{"window": "5h"}, "junk"]}]}}}) == []
