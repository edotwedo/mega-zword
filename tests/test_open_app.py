"""B13: plain `megazword` opens the app window; `megazword start` is the text screen."""

import io

from megazword import cli, config


class TTY(io.StringIO):
    def isatty(self):
        return True


def test_plain_megazword_opens_app_at_a_terminal(tmp_path, monkeypatch):
    launched = []
    monkeypatch.delenv("MEGAZWORD_NO_APP")
    monkeypatch.setattr(cli, "launch_app", lambda: launched.append(True))
    out = TTY()
    monkeypatch.setattr(cli.sys, "stdout", out)
    assert cli.main([], cfg=config.Config(log_path=tmp_path / "log.jsonl")) == 0
    assert launched == [True]
    assert "opening the Mega Zword app" in out.getvalue()


def test_no_app_env_or_pipe_keeps_start_screen(tmp_path, monkeypatch, capsys):
    launched = []
    monkeypatch.setattr(cli, "launch_app", lambda: launched.append(True))
    cfg = config.Config(log_path=tmp_path / "log.jsonl")
    monkeypatch.setattr(cli.sys, "stdout", TTY())
    assert not cli.opens_app()  # MEGAZWORD_NO_APP=1 from conftest
    monkeypatch.delenv("MEGAZWORD_NO_APP")
    monkeypatch.setattr(cli.sys, "stdout", io.StringIO())  # a pipe, not a terminal
    assert not cli.opens_app()
    assert cli.main([], cfg=cfg) == 0
    assert launched == []


def test_start_command_shows_text_screen(tmp_path, monkeypatch, capsys):
    launched = []
    monkeypatch.setattr(cli, "launch_app", lambda: launched.append(True))
    assert cli.main(["start"], cfg=config.Config(log_path=tmp_path / "log.jsonl")) == 0
    assert launched == [] and capsys.readouterr().out.strip()


def test_launch_app_is_detached_and_silent(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli.subprocess, "Popen", lambda cmd, **kw: seen.update(cmd=cmd, **kw))
    cli.launch_app()
    assert "dashboard', '--app'" in seen["cmd"][-1]
    assert seen["stdout"] is cli.subprocess.DEVNULL and seen["stdin"] is cli.subprocess.DEVNULL
