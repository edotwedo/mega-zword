from types import SimpleNamespace

from megazword import cli, doctor
from megazword.usage_sources import PlanUsage


def fake_external(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/fake/{name}")
    monkeypatch.setattr(doctor.subprocess, "run", lambda args, **kwargs:
                        SimpleNamespace(returncode=0, stdout="version 1\n", stderr=""))
    monkeypatch.setattr(doctor.ollama, "reachable", lambda: True)
    monkeypatch.setattr(doctor.ollama, "models", lambda: {"qwen2.5:1.5b"})
    monkeypatch.setattr(doctor.usage_sources, "all_usage", lambda path: [
        PlanUsage("claude", [], "fake"), PlanUsage("codex", [], "fake"),
        PlanUsage("grok", [], "fake")])


def test_doctor_healthy(tmp_path, monkeypatch, capsys):
    fake_external(monkeypatch)
    (tmp_path / "config.toml").write_text('[route]\neasy = ["claude"]\n')
    monkeypatch.setattr(doctor.config, "HOME", tmp_path)
    assert cli.main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert "OK config: parses" in output
    assert "OK rater model: qwen2.5:1.5b present" in output
    assert "OK log: writable" in output
    assert "FAIL" not in output


def test_doctor_warns_without_optional_tools(tmp_path, monkeypatch):
    fake_external(monkeypatch)
    (tmp_path / "config.toml").write_text(
        '[route]\neasy = ["mystery"]\n[out]\ngrok = 2099-01-01\n')
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    monkeypatch.setattr(doctor.ollama, "reachable", lambda: False)
    monkeypatch.setattr(doctor.usage_sources, "all_usage", lambda path: [
        PlanUsage("claude", [], "error", note="SECRET TOKEN")])
    results = doctor.checks(tmp_path)
    lines = "\n".join(item.line() for item in results)
    assert "WARN grok: not on PATH" in lines
    assert "WARN out marks: grok" in lines
    assert "WARN routes: mystery" in lines
    assert "WARN Ollama: unreachable" in lines
    assert "WARN rater model: cannot check" in lines
    assert "WARN claude meter: unreadable" in lines
    assert "SECRET TOKEN" not in lines


def test_doctor_fails_for_bad_config_and_log(tmp_path, monkeypatch):
    fake_external(monkeypatch)
    (tmp_path / "config.toml").write_text("broken = [")
    (tmp_path / "log.jsonl").mkdir()
    results = doctor.checks(tmp_path)
    assert any(c.name == "config" and c.level == "FAIL" for c in results)
    assert any(c.name == "log" and c.level == "FAIL" for c in results)
    monkeypatch.setattr(doctor.config, "HOME", tmp_path)
    assert doctor.run() == 1


def test_doctor_free_keys_and_routes(tmp_path, monkeypatch):
    fake_external(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-test-credential")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    (tmp_path / "config.toml").write_text('[route]\neasy = ["openrouter", "groq"]\n')
    lines = [item.line() for item in doctor.checks(tmp_path)]
    assert lines.count("OK openrouter: key set") == 1
    assert lines.count("WARN groq: key not set") == 1
    assert "OK routes: known backends only" in lines
    assert "secret-test-credential" not in "\n".join(lines)
