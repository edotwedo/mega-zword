"""Renaming the terminal tab from a hidden tool shell (Cinder-21, 2026-10-19).

A bot runs below a hidden console, so it cannot see or set the tab Phil looks
at. These cover the walk that finds the real tab shell, the keeper loop, and the
state file. The Windows console calls themselves are exercised by hand.
"""

import os

import pytest

from megazword import config, tab_title


class FakeProc:
    def __init__(self, pid, name, parent=None):
        self.pid = pid
        self._name = name
        self._parent = parent

    def name(self):
        return self._name

    def parent(self):
        return self._parent


class BrokenProc:
    pid = 9

    def name(self):
        return "x"

    def parent(self):
        raise OSError("access denied")


needs_windows = pytest.mark.skipif(os.name != "nt", reason="Windows console API")


@needs_windows
def test_tab_pid_finds_the_shell_windows_terminal_hosts():
    terminal = FakeProc(1, "WindowsTerminal.exe")
    tab_shell = FakeProc(2, "powershell.exe", terminal)
    node = FakeProc(3, "node.exe", tab_shell)
    cmd = FakeProc(4, "cmd.exe", node)
    me = FakeProc(5, "python.exe", cmd)
    assert tab_title.tab_pid(me) == 2


@needs_windows
def test_tab_pid_asks_for_the_parent_when_no_terminal_is_above():
    explorer = FakeProc(1, "explorer.exe")
    tab_shell = FakeProc(2, "powershell.exe", explorer)
    assert tab_title.tab_pid(tab_shell) == 0


@needs_windows
def test_tab_pid_gives_up_on_a_broken_chain():
    assert tab_title.tab_pid(BrokenProc()) == 0


def test_state_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    assert tab_title.read_state() == {}
    tab_title.write_state(title="Cinder-21", tab_pid=7, keeper_pid=None, stop=False)
    state = tab_title.read_state()
    assert state["title"] == "Cinder-21"
    assert state["tab_pid"] == 7


def test_state_survives_a_corrupt_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    tab_title.state_path().parent.mkdir(parents=True, exist_ok=True)
    tab_title.state_path().write_text("{ not json", encoding="utf-8")
    assert tab_title.read_state() == {}


def _fake_keep(**overrides):
    calls = []
    kwargs = dict(
        attach=lambda pid: pid == 42,
        setter=lambda title: calls.append(title) or True,
        alive=lambda pid: True,
        sleep=lambda _: None,
        stop=lambda: False,
    )
    kwargs.update(overrides)
    return calls, kwargs


def test_keep_reapplies_while_the_tab_lives():
    calls, kwargs = _fake_keep()
    ticks = {"n": 0}
    alive = {"v": True}

    def sleep(_):
        ticks["n"] += 1
        if ticks["n"] >= 3:
            alive["v"] = False

    kwargs["alive"] = lambda pid: alive["v"]
    kwargs["sleep"] = sleep
    assert tab_title.keep("Cinder-21", 42, **kwargs) == 0
    assert calls == ["Cinder-21"] * 3


def test_keep_sets_nothing_when_asked_to_stop():
    calls, kwargs = _fake_keep(stop=lambda: True)
    assert tab_title.keep("Cinder-21", 42, **kwargs) == 0
    assert calls == []


def test_keep_reports_when_it_cannot_attach():
    calls, kwargs = _fake_keep(attach=lambda pid: False)
    assert tab_title.keep("Cinder-21", 42, **kwargs) == 1
    assert calls == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX terminal")
def test_posix_title_writes_osc_to_tty(tmp_path, monkeypatch):
    import builtins

    target = tmp_path / "tty"
    real_open = builtins.open
    monkeypatch.delenv("KITTY_LISTEN_ON", raising=False)
    monkeypatch.setattr(builtins, "open", lambda *a, **kw: real_open(target, "w", **kw))
    assert tab_title.apply_title("Gavin-27")
    assert target.read_bytes() == b"\x1b]2;Gavin-27\x07"


@pytest.mark.skipif(os.name == "nt", reason="POSIX terminal")
def test_posix_title_falls_back_to_stdout(monkeypatch, capsys):
    import builtins

    def unavailable(*args, **kwargs):
        raise OSError("no controlling tty")

    monkeypatch.delenv("KITTY_LISTEN_ON", raising=False)
    monkeypatch.setattr(builtins, "open", unavailable)
    assert tab_title.apply_title("Gavin-27")
    assert capsys.readouterr().out == "\x1b]2;Gavin-27\x07"


@pytest.mark.skipif(os.name == "nt", reason="POSIX terminal")
@pytest.mark.parametrize("returncode", [0, 1])
def test_posix_prefers_kitty_with_osc_fallback(monkeypatch, capsys, returncode):
    import builtins
    from types import SimpleNamespace

    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=returncode)

    def unavailable(*args, **kwargs):
        raise OSError("no tty")

    monkeypatch.setenv("KITTY_LISTEN_ON", "unix:/tmp/kitty-test")
    monkeypatch.setattr(tab_title.subprocess, "run", run)
    monkeypatch.setattr(builtins, "open", unavailable)
    assert tab_title.apply_title("Gavin-27")
    assert calls == [["kitten", "@", "set-tab-title", "Gavin-27"]]
    assert capsys.readouterr().out == ("" if returncode == 0 else "\x1b]2;Gavin-27\x07")


@pytest.mark.skipif(os.name == "nt", reason="POSIX terminal")
def test_posix_keeper_restores_a_reset_title(monkeypatch, capsys):
    import builtins

    def unavailable(*args, **kwargs):
        raise OSError("no tty")

    ticks = []

    def reset(_):
        print("\x1b]2;reset\x07", end="")
        ticks.append(1)

    monkeypatch.delenv("KITTY_LISTEN_ON", raising=False)
    monkeypatch.setattr(builtins, "open", unavailable)
    assert tab_title.keep("Gavin-27", 42, alive=lambda _: len(ticks) < 2,
                          sleep=reset, stop=lambda: False) == 0
    assert capsys.readouterr().out == (
        "\x1b]2;Gavin-27\x07\x1b]2;reset\x07" * 2
    )
