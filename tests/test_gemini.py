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
    monkeypatch.setattr(backends.shutil, "which", lambda name: "fake-gemini.cmd")
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
                        f"/fake/{name}" if installed else None)
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
    assert "gemini  -  plan usage not tracked yet" in output
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
