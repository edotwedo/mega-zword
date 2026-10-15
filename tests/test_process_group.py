"""Windows AI CLIs must not flash a console from the windowless app."""

import os
import subprocess
import sys
import time
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


def test_short_helpers_use_no_console_flag_on_windows(monkeypatch):
    monkeypatch.setattr(backends, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    assert backends.no_window() == {"creationflags": 0x08000000}


def _pid_alive(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return code.value == 259  # STILL_ACTIVE
        return True
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def test_kill_tree_kills_grandchild(tmp_path):
    """A timed-out CLI is a .cmd/.exe shim plus a child (node). Both must die."""
    marker = tmp_path / "child.pid"
    nested = (
        "import os, sys, time, pathlib\n"
        "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()), encoding='utf-8')\n"
        "time.sleep(60)\n"
    )
    parent = (
        "import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]])\n"
        "time.sleep(60)\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", parent, nested, str(marker)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        **backends.process_group(),
    )
    try:
        for _ in range(50):
            if marker.exists():
                break
            time.sleep(0.05)
        assert marker.exists(), "grandchild never started"
        child_pid = int(marker.read_text(encoding="utf-8"))
        assert _pid_alive(proc.pid)
        assert _pid_alive(child_pid)
        backends._kill_tree(proc)
        assert not _pid_alive(proc.pid)
        assert not _pid_alive(child_pid)
    finally:
        backends._kill_tree(proc)


def test_windows_cleanup_also_hides_its_console(monkeypatch):
    calls = []
    monkeypatch.setattr(backends, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append((cmd, kw)))
    proc = SimpleNamespace(pid=123, communicate=lambda **kw: None)
    backends._kill_tree(proc)
    assert calls[0][0] == ["taskkill", "/PID", "123", "/T", "/F"]
    assert calls[0][1]["creationflags"] == subprocess.CREATE_NO_WINDOW
