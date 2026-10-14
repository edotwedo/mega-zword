"""Codex's child PATH workaround, with no real AI or shell launches."""

import os
from dataclasses import replace
from pathlib import Path

import pytest

from megazword import backends


@pytest.mark.parametrize("platform, name, edit", [
    ("win32", "codex", False),
    ("win32", "codex", True),  # Night Shift uses this backend, with a work cwd.
    ("linux", "codex", True),
    ("darwin", "codex", False),
    ("win32", "claude", False),
    ("win32", "grok", False),
    ("win32", "gemini", False),
])
def test_child_environment(monkeypatch, tmp_path, platform, name, edit):
    keep = [r"C:\Windows\System32\WindowsPowerShell\v1.0",
            r"C:\Tools\node", "", r"C:\Other Tools"]
    remove = [r"C:\Users\Phil\AppData\Local\Microsoft\WindowsApps",
              r"C:\Program Files\PowerShell\7",
              r"C:\PROGRAM FILES\POWERSHELL\7-preview",
              "C:/Program Files/PowerShell/7",
              r"C:\Program Files\WINDOWSAPPS\Microsoft.PowerShell_7"]
    original_path = ";".join([keep[0], *remove, *keep[1:]])
    monkeypatch.setenv("PATH", original_path)
    monkeypatch.setenv("MEGAZWORD_ENV_TEST", "preserved")
    monkeypatch.setattr(backends.sys, "platform", platform)
    monkeypatch.setattr(backends.shutil, "which", lambda exe: str(tmp_path / "fake-ai.cmd"))
    backend = backends.default_backends(edit=edit, free_models={})[name]
    if edit:
        # This is also how Night._work prepares its Codex job.
        backend = replace(backend, cwd=str(tmp_path), timeout=31)
    before = dict(os.environ)
    calls = []

    class Process:
        returncode = 0

        def __init__(self, cmd, **kwargs):
            calls.append((cmd, kwargs))
            if "-o" in cmd:
                Path(cmd[cmd.index("-o") + 1]).write_text("fake answer", encoding="utf-8")

        def communicate(self, stdin, timeout):
            assert timeout == backend.timeout
            return "fake answer", ""

    monkeypatch.setattr(backends.subprocess, "Popen", Process)
    result = backend.run("hello")
    assert result.ok, result.error
    assert result.text == "fake answer"
    assert len(calls) == 1
    cmd, kwargs = calls[0]
    assert kwargs["cwd"] == (str(tmp_path) if edit else None)
    env = kwargs["env"]
    if platform == "win32" and name == "codex":
        assert env is not os.environ
        assert env["PATH"] == ";".join(keep)
        assert {key: value for key, value in env.items() if key != "PATH"} == {
            key: value for key, value in before.items() if key != "PATH"}
        assert cmd[cmd.index("-s") + 1] == ("workspace-write" if edit else "read-only")
    else:
        assert env is None
    assert dict(os.environ) == before


@pytest.mark.parametrize("environment", [{}, {"Path": r"C:\Windows;C:\WINDOWSAPPS"},
                                         {"PATH": ""}, {"PATH": r"C:\Tools"}])
def test_windows_path_missing_empty_or_mixed_case(monkeypatch, environment):
    monkeypatch.setattr(backends.sys, "platform", "win32")
    monkeypatch.setattr(backends.os, "environ", environment)
    env = backends.CodexBackend("codex", exe="codex")._env()
    assert env is not environment
    assert env == ({"Path": r"C:\Windows"} if "Path" in environment else environment)
