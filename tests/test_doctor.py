from types import SimpleNamespace
import urllib.error

import pytest

from megazword import cli, doctor
from megazword.usage_sources import PlanUsage


def fake_external(monkeypatch):
    monkeypatch.setenv("MEGAZWORD_OFFLINE", "1")
    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/fake/{name}")
    monkeypatch.setattr(doctor.subprocess, "run", lambda args, **kwargs:
                        SimpleNamespace(returncode=0, stdout="version 1\n", stderr=""))
    monkeypatch.setattr("megazword.backends.run_quick", lambda cmd, timeout:
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
    assert "megazword floor (seats)" in output
    assert "megazword floor suggest" in output
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
    assert lines.count("WARN cloudflare: key not set") == 1
    assert lines.count("WARN mistral: key not set") == 1
    assert "OK routes: known backends only" in lines
    assert "secret-test-credential" not in "\n".join(lines)


@pytest.mark.parametrize("body", ['[route]\neasy = 42\n',
                                   '[route]\neasy = [42]\n',
                                   'rater_model = 42\n'])
def test_doctor_reports_invalid_config_types(tmp_path, monkeypatch, body):
    fake_external(monkeypatch)
    (tmp_path / "config.toml").write_text(body)
    checks = doctor.checks(tmp_path)
    assert any(c.name == "config" and c.level == "FAIL" for c in checks)
    assert any(c.name == "log" for c in checks)


def test_meter_error_names_type_and_code_only():
    from megazword.doctor import _meter_error
    assert _meter_error("HTTPError: HTTP Error 401: Unauthorized") == "unreadable (HTTPError 401)"
    assert _meter_error("FileNotFoundError: [Errno 2] No such file") == "unreadable (FileNotFoundError)"
    assert _meter_error("SECRET TOKEN") == "unreadable"
    assert _meter_error("") == "unreadable"


def room_setup(monkeypatch):
    monkeypatch.setenv("MEGAZWORD_SEAT", "Briar-20")
    monkeypatch.delenv("HIVE_ROOM_URL", raising=False)
    monkeypatch.delenv("MEGAZWORD_OFFLINE", raising=False)
    monkeypatch.delenv("MZ_SMOKE_PYTHON", raising=False)
    monkeypatch.delenv("MEGAZWORD_NTFY_PC_TOPIC", raising=False)
    credentials = {"HIVE_ROOM_KEY_BRIAR_20": "fake-seat-secret",
                   "HIVE_ROOM_TOKEN": "fake-shared-secret",
                   "DISCORD_WEBHOOK": "https://discord.invalid/fake-webhook-secret"}
    monkeypatch.setattr(doctor, "get_key", credentials.get)
    cfg = doctor.config.Config()
    cfg.room_url = "https://room.invalid"
    cfg.room_ntfy_pc_topic = "fake-private-pc-topic"
    cfg.room_ntfy_phone_topic = "fake-private-phone-topic"
    return cfg, credentials


def room_lines(cfg, **kwargs):
    return "\n".join(check.line() for check in doctor.room_checks(cfg, **kwargs))


def test_room_health_authenticates_this_seat_without_printing_secrets(monkeypatch):
    cfg, credentials = room_setup(monkeypatch)
    requests = []

    class Reply:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_): pass

    class Opener:
        def open(self, request, timeout):
            requests.append((request, timeout))
            return Reply()

    def build(handler):
        assert handler.redirect_request(None, None, 302, None, None, "https://other.invalid") is None
        return Opener()

    monkeypatch.setattr(doctor.urllib.request, "build_opener", build)
    lines = room_lines(cfg)
    assert len(requests) == 1
    request, timeout = requests[0]
    assert timeout == 3
    assert request.full_url == "https://room.invalid/rooms/hive/messages?limit=1"
    assert request.get_method() == "GET"
    assert request.get_header("Authorization") == "Bearer fake-seat-secret"
    assert request.get_header("User-agent") == "megazword-room/1"
    assert "OK room URL: configured" in lines
    assert "OK room seat key: per-seat key present" in lines
    assert "OK room authentication: seat token accepted" in lines
    assert "OK room NTFY PC: topic set" in lines
    assert "OK room NTFY phone: topic set" in lines
    assert "OK DISCORD_WEBHOOK: configured (not tested)" in lines
    for secret in (*credentials.values(), cfg.room_ntfy_pc_topic, cfg.room_ntfy_phone_topic):
        assert secret not in lines


def test_room_missing_seat_key_does_not_probe_with_shared_fallback(monkeypatch):
    cfg, credentials = room_setup(monkeypatch)
    del credentials["HIVE_ROOM_KEY_BRIAR_20"]
    monkeypatch.setattr(doctor.urllib.request, "build_opener", lambda *_: pytest.fail("network attempted"))
    lines = room_lines(cfg)
    assert "FAIL room seat key: per-seat key missing" in lines
    assert "WARN room authentication: skipped" in lines


@pytest.mark.parametrize("mode", ["offline", "fake", "argument"])
def test_room_live_probe_can_be_disabled_with_fake_credentials(monkeypatch, mode):
    cfg, _ = room_setup(monkeypatch)
    if mode == "offline": monkeypatch.setenv("MEGAZWORD_OFFLINE", "1")
    if mode == "fake": monkeypatch.setenv("MZ_SMOKE_PYTHON", "fake-python")
    monkeypatch.setattr(doctor.urllib.request, "build_opener", lambda *_: pytest.fail("network attempted"))
    assert "WARN room authentication: skipped (offline/fake mode)" in room_lines(cfg, live=mode != "argument")


@pytest.mark.parametrize("code", [401, 403, 302, 503])
def test_room_probe_http_failures_do_not_expose_error_text(monkeypatch, code):
    cfg, _ = room_setup(monkeypatch)

    def fail(*_args, **_kwargs):
        raise urllib.error.HTTPError("https://fake-seat-secret.invalid", code,
                                     "fake-seat-secret", {}, None)

    monkeypatch.setattr(doctor.urllib.request, "build_opener", lambda *_: SimpleNamespace(open=fail))
    lines = room_lines(cfg)
    assert f"FAIL room authentication: HTTP {code}" in lines
    assert "fake-seat-secret" not in lines


@pytest.mark.parametrize("error", [TimeoutError("fake-seat-secret"), OSError("fake-seat-secret")])
def test_room_probe_transport_failures_are_bounded_and_redacted(monkeypatch, error):
    cfg, _ = room_setup(monkeypatch)

    def fail(_request, timeout):
        assert timeout == 3
        raise error

    monkeypatch.setattr(doctor.urllib.request, "build_opener", lambda *_: SimpleNamespace(open=fail))
    lines = room_lines(cfg)
    assert "FAIL room authentication: probe failed or timed out" in lines
    assert "fake-seat-secret" not in lines


@pytest.mark.parametrize("url", ["", "http://room.invalid", "https://user:fake-secret@room.invalid",
                                 "https://room.invalid/mcp/fake-secret", "https://room.invalid?fake-secret",
                                 "https://room.invalid:bad"])
def test_room_missing_or_invalid_url_never_receives_credentials(monkeypatch, url):
    cfg, _ = room_setup(monkeypatch)
    cfg.room_url = url
    monkeypatch.setattr(doctor.urllib.request, "build_opener", lambda *_: pytest.fail("network attempted"))
    lines = room_lines(cfg)
    assert ("WARN room URL: not configured" if not url else "FAIL room URL: invalid HTTPS origin") in lines
    assert "fake-secret" not in lines


def test_room_unconfigured_seat_topics_and_webhook_warn(monkeypatch):
    cfg, credentials = room_setup(monkeypatch)
    monkeypatch.delenv("MEGAZWORD_SEAT")
    credentials.clear()
    cfg.room_ntfy_pc_topic = cfg.room_ntfy_phone_topic = ""
    lines = room_lines(cfg, live=False)
    assert "WARN room seat key: seat not set" in lines
    assert "WARN room NTFY PC: topic not set" in lines
    assert "WARN room NTFY phone: topic not set" in lines
    assert "WARN DISCORD_WEBHOOK: not configured" in lines


def test_room_environment_url_and_pc_topic_override_config(monkeypatch):
    cfg, _ = room_setup(monkeypatch)
    monkeypatch.setenv("HIVE_ROOM_URL", "https://override.invalid")
    monkeypatch.setenv("MEGAZWORD_NTFY_PC_TOPIC", "private-env-topic")
    cfg.room_url = "bad"
    cfg.room_ntfy_pc_topic = ""
    lines = room_lines(cfg, live=False)
    assert "OK room URL: configured" in lines and "OK room NTFY PC: topic set" in lines
    assert "private-env-topic" not in lines


def test_doctor_includes_room_health_and_supports_offline_argument(tmp_path, monkeypatch):
    fake_external(monkeypatch)
    monkeypatch.setattr(doctor, "get_key", lambda _: None)
    results = doctor.checks(tmp_path, live_room=False)
    names = {check.name for check in results}
    assert {"room URL", "room seat key", "room authentication", "room NTFY PC",
            "room NTFY phone", "DISCORD_WEBHOOK"} <= names
    assert all(check.level in {"OK", "WARN", "FAIL"} for check in results)
