"""Windows AI CLIs must not flash a console from the windowless app."""

import os
import subprocess
from types import SimpleNamespace

from megazword.backends import process_group
from megazword import backends


def test_process_group_hides_console_on_windows():
    flags = process_group()
    if os.name == "nt":
        hidden = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        assert flags["creationflags"] == hidden
    else:
        assert flags.get("start_new_session") is True


def test_windows_cleanup_also_hides_its_console(monkeypatch):
    calls = []
    monkeypatch.setattr(backends, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append((cmd, kw)))
    proc = SimpleNamespace(pid=123, communicate=lambda **kw: None)
    backends._kill_tree(proc)
    assert calls[0][0] == ["taskkill", "/PID", "123", "/T", "/F"]
    assert calls[0][1]["creationflags"] == subprocess.CREATE_NO_WINDOW
