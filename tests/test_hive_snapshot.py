"""The Linux restore: the snapshot, and the properties that actually broke.

On 2026-10-26 all five CLI windows on Phil's box carried the same exported
``MEGAZWORD_SEAT`` (they were children of one shell that had it set), so every tab came up
as Gavin-27 and nothing could tell the seats apart. Identity has to belong to the tab, so
the tests below check that each seat's launch names its own designation and that the
snapshot never writes to a shared profile. On 2026-10-30 that bug was found LIVE again - three
tabs claiming Gavin-27 - which is what the seat count now catches.

On 2026-10-30 the restore also turned out to have been dead for days in three silent ways: the
script was not executable, it had CRLF line endings, and ``kitty_tab_commands`` built its own
CLI line so only the FIRST seat kept a pinned model. So the host kitty is seatless, one helper
builds every CLI argv, every seat launches the same way, and there is a seat count.

The restore itself is one kitty with remote control plus a `kitten @ launch` per seat. A kitty
session file was tried first and kitty 0.49.2 rejects it outright - see the snapshot script's
docstring - so these tests pin the working form.
"""

import importlib.util
import os
import shlex
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


def _tabs(*designations, title="seat", pid=None):
    """A kitty @ ls dump. pid defaults to THIS process, so the seats read as genuinely live."""
    live_pid = os.getpid() if pid is None else pid
    return [{"tabs": [
        {"id": i, "title": f"{title}{i}",
         "windows": [{"env": {"MEGAZWORD_SEAT": designation}, "pid": live_pid}]}
        for i, designation in enumerate(designations, start=1)
    ]}]


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


def test_the_kitty_we_start_carries_no_seat():
    """`kitty -e <cmd>` dies when <cmd> dies, and the control socket dies with it - so a seat
    riding in the host made ONE seat's health a liveness dependency for every other seat."""
    start = snapshot.kitty_start_command("/tmp/hive.sock")
    assert start.startswith("kitty ")
    assert "--listen-on unix:/tmp/hive.sock" in start
    assert "allow_remote_control=yes" in start
    assert snapshot.HOST_TITLE in start
    assert snapshot.HOST_HOLD in start


def test_the_host_hold_is_one_quoted_argument():
    """The show-stopper grok caught in my own fix (2026-10-30): unquoted, `sh -c` receives only
    `exec`, `sleep 86400` becomes $0/$1, exec no-ops, the host exits immediately and takes the
    socket - and every launch - down with it."""
    start = snapshot.kitty_start_command("/tmp/hive.sock")
    assert shlex.quote(snapshot.HOST_HOLD) in start
    assert snapshot.HOST_HOLD.startswith("env -u MEGAZWORD_SEAT"), \
        "a restore run from a seat's tab must not let the host inherit that seat"
    assert "MEGAZWORD_SEAT" not in start.replace(snapshot.HOST_HOLD, ""), \
        "the only mention of the seat var may be the env -u guard"


def test_every_seat_launches_the_same_way_and_a_new_group_opens_an_os_window():
    commands = snapshot.kitty_tab_commands(STATE, "/tmp/hive.sock")
    assert len(commands) == 3, "every seat launches as a tab, the first one included"
    assert "--type=tab" in commands[0] and "--env=MEGAZWORD_SEAT=Gavin-27" in commands[0]
    # MIKE starts window 2, so his launch opens it; Paul joins that window as a tab.
    assert "--type=os-window" in commands[1] and "--env=MEGAZWORD_SEAT=MIKE-54" in commands[1]
    assert "--type=tab" in commands[2] and "--env=MEGAZWORD_SEAT=Paul-53" in commands[2]
    for command in commands:
        assert "--to unix:/tmp/hive.sock" in command
        assert "--cwd=/work" in command


def test_a_pinned_model_survives_on_every_seat_not_just_the_first(monkeypatch):
    """The 2026-10-30 bug: kitty_tab_commands built its own CLI line, so only the seat in the
    host kept its model and every seat after it silently reverted to the CLI's default."""
    monkeypatch.setattr(snapshot.resume, "find_session", lambda *a, **k: "")
    state = snapshot.layout("/tmp/x")
    state["tabs"][1]["model"] = "poolside/laguna-s-2.1-free"
    assert "--model poolside/laguna-s-2.1-free" not in snapshot.kitty_start_command()
    assert "--model poolside/laguna-s-2.1-free" in snapshot.kitty_tab_commands(state)[1]


def test_one_helper_builds_the_argv_so_the_two_paths_cannot_diverge():
    """The model bug was caused by duplicating this list. Both paths must come from _cli_argv."""
    tab = {"designation": "Gilbert-6969", "name": "Gilbert", "cli": "cmdc",
           "dir": "/work", "group": 1, "session": "", "model": "poolside/laguna-s-2.1-free"}
    assert snapshot._cli_argv(tab) == ["cmdc", "-c", "--model", "poolside/laguna-s-2.1-free"]


def test_agy_is_resumed_by_its_conversation_id():
    commands = snapshot.kitty_tab_commands(STATE, "/tmp/hive.sock")
    assert "--conversation 69bf406f-0726-46de-808b-8f1acdc67930" in commands[1]


def test_each_seat_is_told_its_own_working_directory(tmp_path):
    state = snapshot.layout(str(tmp_path))
    # A seat with a `dir` of its own keeps it: Gavin-27's cmdc conversation is filed under
    # $HOME, not the repo, so his session is only found there (2026-10-26). Every other seat
    # falls back to the workdir it was handed.
    dirs = {tab["designation"]: tab["dir"] for tab in state["tabs"]}
    for seat in snapshot.SEATS:
        assert dirs[seat["designation"]] == seat.get("dir", str(tmp_path))
    mike = next(c for c in snapshot.kitty_tab_commands(state) if "MIKE-54" in c)
    assert f"--cwd={tmp_path}" in mike


def test_only_filters_before_session_lookup(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(snapshot.resume, "find_session",
                        lambda *args: calls.append(args) or "")
    assert snapshot.main(["--only", "mike-54", "--print"]) == 0
    output = capsys.readouterr().out
    assert "MEGAZWORD_SEAT=MIKE-54" in output
    assert "Gavin-27" not in output
    # one seat tab, added to the seatless host
    assert output.count("kitten @") == 1
    assert len(calls) == 1 and calls[0][2] == "MIKE-54"


def test_unknown_only_is_rejected(capsys):
    import pytest
    with pytest.raises(SystemExit) as error:
        snapshot.main(["--only", "unknown", "--print"])
    assert error.value.code == 2
    assert "unknown seat" in capsys.readouterr().err


def test_the_host_is_found_by_title_not_by_a_missing_seat_variable():
    """`kitty @ ls` reports the PROCESS env and omits variables identical on every window, so a
    tab with no MEGAZWORD_SEAT can still be a real seat. Matching host on that would close it -
    which is what the live box nearly did (grok review, 2026-10-30)."""
    dump = [{"tabs": [
        {"id": 1, "title": snapshot.HOST_TITLE, "windows": [{"env": {}}]},
        {"id": 2, "title": "WenWei", "windows": [{"env": {}}]},          # CLI not up yet
        {"id": 3, "title": "Gavin", "windows": [{"env": {"MEGAZWORD_SEAT": "Gavin-27"}}]},
    ]}]
    seats, host_tabs = snapshot.seats_in_kitty(dump)
    assert host_tabs == [1], "only the titled host may ever be closed"
    assert [designation for designation, _ in seats] == ["Gavin-27"]


def test_a_seat_whose_cli_died_is_not_counted_as_up(monkeypatch):
    """Gilberg-6969's finding (2026-10-30): the env says what was LAUNCHED, so without checking
    the process a crashed CLI in a live tab still reads as a healthy seat."""
    monkeypatch.setattr(snapshot, "kitty_ls", lambda *a, **k: _tabs("Gavin-27", "MIKE-54", "Paul-53"))
    monkeypatch.setattr(snapshot, "_alive", lambda pid: False)
    report, ok = snapshot.seat_report(STATE)
    assert ok is False
    assert "EXITED" in report


def test_the_liveness_check_asks_the_os_about_a_real_pid():
    assert snapshot._alive(os.getpid()) is True
    assert snapshot._alive(None) is False
    assert snapshot._alive(0) is False


def test_the_seat_report_names_what_did_not_come_up(monkeypatch):
    monkeypatch.setattr(snapshot, "kitty_ls", lambda *a, **k: _tabs("Gavin-27"))
    report, ok = snapshot.seat_report(STATE)
    assert ok is False
    assert "1/3" in report
    assert "MIKE-54" in report and "Paul-53" in report


def test_two_tabs_wearing_one_designation_fail_the_count(monkeypatch):
    """The live box did exactly this on 2026-10-30: three tabs all carrying Gavin-27, so a
    set-of-names count would have called it healthy."""
    monkeypatch.setattr(snapshot, "kitty_ls", lambda *a, **k: _tabs("Gavin-27", "Gavin-27", "MIKE-54"))
    report, ok = snapshot.seat_report(STATE)
    assert ok is False
    assert "DUPLICATED" in report and "Gavin-27" in report


def test_the_seat_report_passes_when_every_seat_came_up(monkeypatch):
    monkeypatch.setattr(snapshot, "kitty_ls", lambda *a, **k: _tabs("Gavin-27", "MIKE-54", "Paul-53"))
    report, ok = snapshot.seat_report(STATE)
    assert ok is True
    assert report == "seats up: 3/3"


def test_a_missing_kitty_is_not_an_exception():
    """Counting seats must never be the thing that breaks a restore."""
    assert snapshot.kitty_ls("/nonexistent/hive.sock") == []
