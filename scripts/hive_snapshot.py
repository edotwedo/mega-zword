#!/usr/bin/env python3
"""Snapshot the Hive's live CLI windows, so a reboot can put them back.

Phil, 2026-10-26: "i need it to literally open it JUST like it is RIGHT NOW. i don't
care how. saved state, some sort of snap shot i do not care. just make it happen."

  ~/.megazword/hive-layout.json     the snapshot: each seat, its directory, CLI and the
                                    conversation to resume, plus which OS window it sits in

The restore is scripts/hive_resume.sh, which starts one kitty and adds the other seats to it.
Two things this does that the Windows launcher never had to:

- The seat table is per-machine. The Windows seats and the Linux seats are different people
  with different tools, so this file names the Linux team only. Nothing here can start a
  Windows seat on this box.
- Every tab is launched with its OWN MEGAZWORD_SEAT. That is what broke: the four non-cmdc
  windows all inherited one exported MEGAZWORD_SEAT and every tab came up as Gavin-27 (found
  in the process table, 2026-10-26). The seat is set on the tab's own launch, so it cannot
  leak into another tab, and nothing writes to a shared profile.

Methods that were tried and did NOT work, so nobody repeats them (measured, 2026-10-26):

- A kitty *session file*. It is the natural fit and kitty 0.49.2 rejects it: `launch --title`
  and `launch --env` inside a session file make kitty call the whole session invalid (it
  accepts a bare `launch <cmd>` and nothing more), `launch <script-path>` failed the same way,
  and the error is only visible inside the window. `kitten @ launch` accepts those exact
  options, so the restore uses that instead.
- Ghostty. Its CLI has no action that opens a tab at all (`+new-window` is the only one), so
  ghostty can restore the seats but not the tab grouping. It stays as the fallback.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from megazword import config, resume  # noqa: E402

# The Linux team, in tab order, as it actually stands. `group` is which OS window the tab
# lives in: the live layout is one window holding the cmdc tab and a second holding the rest.
# This list is a launcher's lane table, exactly like $lanes in scripts/hive_up.ps1 - it is
# data about THIS machine, not a rule about who exists.
SEATS = (
    # Gavin's cmdc conversation is filed under the HOME directory, not the repo, because the
    # window was opened from $HOME. cmdc scopes sessions to the directory, so a seat that
    # resumes in the repo finds a different cmdc session there (2026-10-26: Gavin came back as
    # 4cc21ea8 instead of his own 52f53b28). A seat's directory must be where its conversation
    # lives; `dir` overrides WORKDIR for exactly that. Every other CLI here keeps its own.
    {"designation": "Gavin-27", "name": "Gavin", "cli": "cmdc", "group": 1,
     "dir": str(Path.home())},
    {"designation": "MIKE-54", "name": "MIKE", "cli": "agy", "group": 2},
    {"designation": "Billy-55", "name": "Billy", "cli": "grok", "group": 2},
    {"designation": "WenWei-56", "name": "WenWei", "cli": "codex", "group": 2},
    {"designation": "Paul-53", "name": "Paul", "cli": "claude", "group": 2},
)

WORKDIR = "/home/edotwedo/workspace/mega-zword"
SOCKET = os.environ.get("MZ_HIVE_SOCKET") or str(
    Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "kitty-hive.sock")


def layout(workdir: str = WORKDIR, only: str | None = None) -> dict:
    """The seats with the session each CLI should resume.

    agy keeps one ``<conversation-id>.db`` per conversation in a global folder, so its newest
    is the newest conversation; the rest are keyed by working directory.
    """
    tabs = []
    for seat in SEATS:
        if only is not None and seat["designation"].casefold() != only.casefold():
            continue
        # A per-seat directory beats the shared workdir: it is where the seat's own
        # conversation lives, which is what the directory-keyed CLIs (cmdc) resume from.
        directory = seat.get("dir", workdir)
        session = seat.get("session") or resume.find_session(
            seat["cli"], directory, seat["designation"]) or ""
        tabs.append({
            "designation": seat["designation"],
            "name": seat["name"],
            "cli": seat["cli"],
            "group": seat["group"],
            "dir": directory,
            "session": session,
        })
    return {"workdir": workdir, "tabs": tabs}


def tab_command(tab: dict) -> str:
    """The command a tab runs: its own seat in its own environment, then the CLI resumed.

    The seat is exported for the CLI process only. A recovered layout must not repeat the
    inherited-variable accident, so nothing here writes to a shared profile.
    """
    args = resume.resume_args(tab["cli"], tab["dir"], tab["session"] or None)
    command = " ".join(shlex.quote(part) for part in [tab["cli"], *args])
    return f"env MEGAZWORD_SEAT={shlex.quote(tab['designation'])} {command}"


def kitty_start_command(state: dict, socket: str = SOCKET) -> str:
    """The one kitty to start, with the first seat already running in its first tab.

    Remote control goes on a socket of our own rather than kitty's default, so the restore
    talks to the instance it started and not to a kitty Phil opened himself.
    """
    first = state["tabs"][0]
    return " ".join([
        "kitty", "-o", "allow_remote_control=yes", "--listen-on", f"unix:{socket}",
        "--detach", "--title", first["name"],
        "-e", "/bin/sh", "-c", shlex.quote(tab_command(first)),
    ])


def kitty_tab_commands(state: dict, socket: str = SOCKET) -> list[str]:
    """``kitten @ launch`` for every seat after the first: one tab each, one window per group.

    `--env` here is what gives each tab its own seat - the same flag kitty refuses inside a
    session file.
    """
    commands = []
    opened = {state["tabs"][0]["group"]}
    for tab in state["tabs"][1:]:
        # The first tab of a new group opens the OS window; its siblings join it as tabs.
        kind = "tab" if tab["group"] in opened else "os-window"
        opened.add(tab["group"])
        args = resume.resume_args(tab["cli"], tab["dir"], tab["session"] or None)
        commands.append(" ".join([
            "kitten", "@", "--to", f"unix:{socket}", "launch",
            f"--type={kind}", f"--title={tab['name']}",
            f"--env=MEGAZWORD_SEAT={tab['designation']}",
            f"--cwd={tab['dir']}",
            tab["cli"], *[shlex.quote(arg) for arg in args],
        ]))
    return commands


def ghostty_commands(state: dict) -> list[str]:
    """One ``ghostty +new-window`` per seat - the fallback when kitty is not installed.

    Ghostty has no CLI action that opens a tab, so this keeps the seats and their
    conversations and loses only the tab grouping.
    """
    commands = []
    for tab in state["tabs"]:
        commands.append(" ".join([
            "ghostty", "+new-window",
            f"--title={tab['name']}",
            f"--working-directory={tab['dir']}",
            "-e", "sh", "-c", shlex.quote(tab_command(tab)),
        ]))
    return commands


def describe(state: dict) -> None:
    """One line per seat: who, which CLI, where, and the conversation coming back."""
    for tab in state["tabs"]:
        if tab["session"]:
            note = tab["session"]
        elif tab["cli"] in resume.HAS_RECENT_FORM:
            note = "continues the newest transcript for this directory"
        else:
            note = "starts fresh (this CLI records no transcript to resume)"
        print(f"{tab['designation']:10} {tab['cli']:7} tab '{tab['name']}' window {tab['group']}  "
              f"resume: {note}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--print", action="store_true", dest="show",
                        help="print the layout and the restore commands; write nothing")
    parser.add_argument("--kitty-start", action="store_true",
                        help="print the kitty command that opens the first seat, and nothing else")
    parser.add_argument("--kitty-tabs", action="store_true",
                        help="print the kitten commands that add the remaining tabs, one per line")
    parser.add_argument("--ghostty", action="store_true",
                        help="print the ghostty fallback commands, one per seat")
    parser.add_argument("--dir", default=WORKDIR, help="working directory for every seat")
    parser.add_argument("--only", metavar="DESIGNATION", help="include only this seat")
    args = parser.parse_args(argv)

    state = layout(args.dir, only=args.only)
    if not state["tabs"]:
        parser.error(f"unknown seat: {args.only}")

    if args.kitty_start:
        print(kitty_start_command(state))
        return 0
    if args.kitty_tabs:
        for command in kitty_tab_commands(state):
            print(command)
        return 0
    if args.ghostty:
        for command in ghostty_commands(state):
            print(command)
        return 0

    describe(state)
    if args.show:
        print()
        print(kitty_start_command(state))
        for command in kitty_tab_commands(state):
            print(command)
        return 0

    snapshot = config.HOME / "hive-layout.json"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {snapshot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
