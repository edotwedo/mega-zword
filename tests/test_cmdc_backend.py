"""The Command Code (cmdc) backend: headless args, sign-in gate, exit handling.

Fakes only: no real cmdc, no network.
"""

from __future__ import annotations

from megazword import backends


class FakeProc:
    def __init__(self, code, out="", err=""):
        self.returncode, self._out, self._err = code, out, err

    def communicate(self, data, timeout=None):
        return self._out, self._err


def fake_cli(monkeypatch, proc):
    monkeypatch.setattr(backends.shutil, "which", lambda exe: "cmdc")
    monkeypatch.setattr(backends, "_kill_tree", lambda *a, **k: None)
    monkeypatch.setattr(backends.subprocess, "Popen", lambda *a, **k: proc)


def test_cmdc_runs_headless_with_full_access():
    b = backends.cmdc_backend()
    assert b.args[:5] == ["-p", "--yolo", "--skip-onboarding", "--no-auto-update", "--max-turns"]
    assert b.args[5] == "60"
    assert "-m" not in b.args  # default model


def test_cmdc_model_flag_is_passed():
    b = backends.cmdc_backend("cmdc-glm", "z-ai/glm-5.3-flash")
    assert b.args[b.args.index("-m") + 1] == "z-ai/glm-5.3-flash"


def test_prompt_goes_on_stdin_not_argv(monkeypatch):
    monkeypatch.setattr(backends.shutil, "which", lambda exe: "cmdc")
    cmd, stdin = backends.cmdc_backend()._command("PROMPT TEXT")
    assert stdin == "PROMPT TEXT"
    assert "PROMPT TEXT" not in cmd


def test_available_needs_the_cli_and_a_login(tmp_path, monkeypatch):
    b = backends.cmdc_backend()
    monkeypatch.setattr(backends.shutil, "which", lambda exe: None)
    assert b.available() is False                          # not installed
    monkeypatch.setattr(backends.shutil, "which", lambda exe: "cmdc")
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    assert b.available() is False                          # installed but signed out
    (tmp_path / ".commandcode").mkdir()
    (tmp_path / ".commandcode" / "auth.json").write_text("{}", encoding="utf-8")
    assert b.available() is True


def test_default_backends_include_cmdc():
    names = set(backends.default_backends(edit=True, free_models={}))
    assert {"cmdc", "cmdc-glm", "cmdc-qwen"} <= names


def test_exit_8_keeps_the_partial_answer(monkeypatch):
    fake_cli(monkeypatch, FakeProc(8, "partial work", "max turns reached"))
    result = backends.cmdc_backend().run("do it")
    assert result.ok is True and result.text == "partial work"


def test_other_clis_still_treat_exit_8_as_failure(monkeypatch):
    fake_cli(monkeypatch, FakeProc(8, "", "max turns reached"))
    result = backends.CLIBackend("claude", exe="claude").run("do it")
    assert result.ok is False and "exited with code 8" in result.error
