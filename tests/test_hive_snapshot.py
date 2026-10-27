"""The Linux restore: the snapshot, and the one property that actually broke.

On 2026-10-26 all five CLI windows on Phil's box carried the same exported
``MEGAZWORD_SEAT`` (they were children of one shell that had it set), so every tab came up
as Gavin-27 and nothing could tell the seats apart. Identity has to belong to the tab, so
the tests below check that each seat's launch names its own designation and that the
snapshot never writes to a shared profile.

The restore itself is one kitty with remote control plus a `kitten @ launch` per seat. A
kitty session file was tried first and kitty 0.49.2 rejects it outright - see the snapshot
script's docstring - so these tests pin the working form.
"""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "hive_snapshot.py"


def _load():
    spec = importlib.util.spec_from_file_location("hive_snapshot", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


snapshot = _load()

# Three seats in two OS windows: the live layout, shrunk.
STATE = {
    "workdir": "/work",
    "tabs": [
        {"designation": "Gavin-27", "name": "Gavin", "cli": "cmdc", "dir": "/work",
         "group": 1, "session": "aaa"},
        {"designation": "MIKE-54", "name": "MIKE", "cli": "agy", "dir": "/work",
         "group": 2, "session": "69bf406f-0726-46de-808b-8f1acdc67930"},
        {"designation": "Paul-53", "name": "Paul", "cli": "claude", "dir": "/work",
         "group": 2, "session": ""},
    ],
}


def test_every_seat_gets_its_own_designation_and_never_a_shared_one(monkeypatch):
    """The bug this exists for: five windows, one inherited seat."""
    monkeypatch.setattr(snapshot.resume, "find_session", lambda *a, **k: "")
    commands = [snapshot.tab_command(tab) for tab in snapshot.layout("/tmp/x")["tabs"]]
    seats = [seat["designation"] for seat in snapshot.SEATS]
    for designation, command in zip(seats, commands):
        assert f"MEGAZWORD_SEAT={designation}" in command
    assert len(set(commands)) == len(commands), "two seats share one command line"
    assert "export" not in " ".join(commands), "nothing may export into a shared shell"


def test_a_tab_command_resumes_the_session_it_was_handed():
    tab = {"designation": "Paul-53", "name": "Paul", "cli": "claude",
           "dir": "/work", "group": 2, "session": "abc"}
    assert snapshot.tab_command(tab) == \
        "env MEGAZWORD_SEAT=Paul-53 claude --permission-mode acceptEdits --resume abc"


def test_a_cli_with_no_session_still_gets_its_own_directory_form():
    """cmdc/claude/grok/codex each have a "newest" form, and using it is better than starting
    a stranger - but it must never be handed another seat's id."""
    tab = {"designation": "WenWei-56", "name": "WenWei", "cli": "codex",
           "dir": "/work", "group": 2, "session": ""}
    assert snapshot.tab_command(tab) == "env MEGAZWORD_SEAT=WenWei-56 codex resume --last"


def test_the_first_seat_rides_in_the_kitty_we_start():
    start = snapshot.kitty_start_command(STATE, "/tmp/hive.sock")
    assert start.startswith("kitty ")
    assert "--listen-on unix:/tmp/hive.sock" in start
    assert "allow_remote_control=yes" in start
    assert "MEGAZWORD_SEAT=Gavin-27" in start


def test_remaining_seats_join_as_tabs_and_a_new_group_opens_an_os_window():
    commands = snapshot.kitty_tab_commands(STATE, "/tmp/hive.sock")
    assert len(commands) == 2
    # MIKE starts window 2, so his launch opens it; Paul joins that window as a tab.
    assert "--type=os-window" in commands[0] and "MIKE-54" in commands[0]
    assert "--type=tab" in commands[1] and "Paul-53" in commands[1]
    for command in commands:
        assert "--to unix:/tmp/hive.sock" in command
        assert "--cwd=/work" in command
    assert "--env=MEGAZWORD_SEAT=MIKE-54" in commands[0]
    assert "--env=MEGAZWORD_SEAT=Paul-53" in commands[1]


def test_agy_is_resumed_by_its_conversation_id():
    commands = snapshot.kitty_tab_commands(STATE, "/tmp/hive.sock")
    assert "--conversation 69bf406f-0726-46de-808b-8f1acdc67930" in commands[0]


def test_each_seat_is_told_its_own_working_directory(tmp_path):
    state = snapshot.layout(str(tmp_path))
    # A seat with a `dir` of its own keeps it: Gavin-27's cmdc conversation is filed under
    # $HOME, not the repo, so his session is only found there (2026-10-26). Every other seat
    # falls back to the workdir it was handed.
    dirs = {tab["designation"]: tab["dir"] for tab in state["tabs"]}
    for seat in snapshot.SEATS:
        assert dirs[seat["designation"]] == seat.get("dir", str(tmp_path))
    # The first seat after Gavin (MIKE) still gets the handed workdir as its cwd.
    assert f"--cwd={tmp_path}" in snapshot.kitty_tab_commands(state)[0]


def test_only_filters_before_session_lookup(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(snapshot.resume, "find_session",
                        lambda *args: calls.append(args) or "")
    assert snapshot.main(["--only", "mike-54", "--print"]) == 0
    output = capsys.readouterr().out
    assert "MEGAZWORD_SEAT=MIKE-54" in output
    assert "Gavin-27" not in output
    assert "kitten @" not in output
    assert len(calls) == 1 and calls[0][2] == "MIKE-54"


def test_unknown_only_is_rejected(capsys):
    import pytest
    with pytest.raises(SystemExit) as error:
        snapshot.main(["--only", "unknown", "--print"])
    assert error.value.code == 2
    assert "unknown seat" in capsys.readouterr().err
