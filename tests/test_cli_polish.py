"""CLI help and ordinary input failures need no installed AIs or network."""

import argparse
import io

import pytest

from megazword import config
from megazword.cli import COMMAND_GROUPS, build_parser, main, save_last_run
from tests.test_cli import FakeBackend


def test_help_lists_every_subcommand_in_its_section(capsys):
    parser = build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    text = capsys.readouterr().out
    assert set(sub.choices) == {n for names in COMMAND_GROUPS.values() for n in names}
    for title, names in COMMAND_GROUPS.items():
        section = text.split(f"{title}:\n", 1)[1].split("\n\n", 1)[0]
        assert {line.split()[0] for line in section.splitlines()} == set(names)
    assert len(text.split("Examples:\n")[1].strip().splitlines()) == 4


def test_command_groups_cover_every_subcommand_once():
    parser = build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    listed = [n for names in COMMAND_GROUPS.values() for n in names]
    assert len(listed) == len(set(listed))
    assert set(listed) == set(sub.choices)


def test_python_dash_m_megazword_runs_cli(monkeypatch, capsys):
    import runpy
    monkeypatch.setattr("sys.argv", ["megazword", "--version"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("megazword", run_name="__main__")
    assert exc.value.code == 0
    assert capsys.readouterr().out.startswith("megazword ")


def test_help_lists_mcp(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "mcp" in capsys.readouterr().out.split("Set up:\n", 1)[1].split("\n\n", 1)[0]


def test_help_mentions_floor_suggest(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    see = capsys.readouterr().out.split("See:\n", 1)[1].split("\n\n", 1)[0]
    assert "suggest" in next(line for line in see.splitlines() if line.split()[0] == "floor")
    with pytest.raises(SystemExit):
        main(["floor", "--help"])
    assert "seated model" in capsys.readouterr().out


@pytest.mark.parametrize("command", [n for ns in COMMAND_GROUPS.values() for n in ns])
def test_subcommand_help_has_description(command, capsys):
    parser = build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    description = sub.choices[command].description
    assert description and "\n" not in description
    with pytest.raises(SystemExit) as exc:
        main([command, "--help"])
    assert exc.value.code == 0
    assert description in capsys.readouterr().out


@pytest.mark.parametrize("args, message", [
    (["out", "grok", "--until", "someday"], "Invalid"),
    (["out", "grok", "--until", "999999999999999999999d"], "too far"),
    (["out", "grok", "--until", "2026-99-99"], "month"),
    (["out", "nobody", "--until", "7d"], "Unknown AI"),
    (["out", "--until", "7d"], "name an AI"),
    (["run", "hi", "-m", "nobody"], "Unknown AI"),
    (["retry", "-m", "nobody"], "Unknown AI"),
    (["run"], "No prompt"),
    (["run", "  "], "No prompt"),
    (["run", "hi", "--compare", "fake,nobody"], "unknown"),
])
def test_bad_input_is_one_line_and_code_2(args, message, capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    if args[0] == "retry":
        save_last_run("hi", "hi", ["fake"], "fake", "answer", "test", None)
    assert main(args, {"fake": FakeBackend("fake")}, config.Config()) == 2
    captured = capsys.readouterr()
    assert not captured.out
    assert len(captured.err.splitlines()) == 1
    assert message.lower() in captured.err.lower()
    assert "Traceback" not in captured.err


def test_missing_prompt_on_terminal_does_not_wait(monkeypatch, capsys):
    class Terminal:
        def isatty(self):
            return True

        def read(self):
            pytest.fail("missing prompt must not wait for terminal input")

    monkeypatch.setattr("sys.stdin", Terminal())
    assert main(["run"], {}, config.Config()) == 2
    assert len(capsys.readouterr().err.splitlines()) == 1


@pytest.mark.parametrize("args", [["note"], ["run", "-m"], ["out", "grok", "--until"]])
def test_missing_arguments_are_one_line(args, capsys):
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2
    assert len(capsys.readouterr().err.splitlines()) == 1
