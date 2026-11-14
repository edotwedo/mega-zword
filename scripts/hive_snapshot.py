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
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from megazword import config, resume  # noqa: E402

# The Linux team, in tab order, as it actually stands. `group` is which OS window the tab
# lives in. All six seats share ONE window today, so every group is 1; give a seat its own
# group number to have the restore open it in a separate OS window instead.
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
    {"designation": "MIKE-54", "name": "MIKE", "cli": "agy", "group": 1},
    {"designation": "Billy-55", "name": "Billy", "cli": "grok", "group": 1},
    {"designation": "WenWei-56", "name": "WenWei", "cli": "codex", "group": 1},
    {"designation": "Paul-53", "name": "Paul", "cli": "claude", "group": 1},
    # Gilbert-6969 (Phil named him 2026-10-29) is the trial seat on a FREE Command Code model.
    # The model is pinned in the seat because trying that model is the entire point of it; cmdc
    # takes -m/--model. Drop the "model" key and he simply runs cmdc's default.
    # His own `dir` matters: cmdc keys conversations by directory, so without it a brand-new
    # seat resolves to the newest cmdc conversation in the shared workdir and comes up wearing
    # somebody else's history. Same trap the Gavin note above describes.
    # DIGIT LIMIT: claims.py DESIGNATION is [A-Za-z]{3,}-?\d{2,4}. "Gilbert-696969" does NOT
    # match, so the seat would be invisible to resume and its claims would never register.
    # Widen that regex before giving anyone a five- or six-digit name.
    {"designation": "Gilbert-6969", "name": "Gilbert", "cli": "cmdc", "group": 1,
     "dir": str(Path.home() / "workspace" / "gilbert"),
     "model": "poolside/laguna-s-2.1-free"},
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
            # Optional: a seat that pins its own model. Absent for every older seat, so their
            # restores stay byte-identical.
            "model": seat.get("model", ""),
        })
    return {"workdir": workdir, "tabs": tabs}


def _cli_argv(tab: dict) -> list[str]:
    """The seat's CLI and its resume flags, pinned model included. ONE place builds this.

    It used to be written twice - once for the host, once inside kitty_tab_commands - and that
    duplication is exactly how a pinned model survived on the first seat and silently vanished
    on every other one (2026-10-30). Never inline this again.
    """
    argv = [tab["cli"], *resume.resume_args(tab["cli"], tab["dir"], tab["session"] or None)]
    if tab.get("model"):
        argv += ["--model", tab["model"]]
    return argv


def tab_command(tab: dict) -> str:
    """The command a tab runs: its own seat in its own environment, then the CLI resumed.

    The seat is exported for the CLI process only. A recovered layout must not repeat the
    inherited-variable accident, so nothing here writes to a shared profile.
    """
    return " ".join([
        f"env MEGAZWORD_SEAT={shlex.quote(tab['designation'])}",
        *[shlex.quote(part) for part in _cli_argv(tab)],
    ])


HOST_TITLE = "sh"
# `env -u` so the host can NEVER inherit a seat when a restore is run from inside a seat's tab.
HOST_HOLD = "env -u MEGAZWORD_SEAT sleep 86400"


def kitty_start_command(socket: str = SOCKET) -> str:
    """The one kitty to start: a SEATLESS host, whose only job is to own the control socket.

    It runs an inert command, not a seat, on purpose. `kitty -e <cmd>` exits when <cmd> exits,
    and the socket lives with the process - so putting the first seat here made that seat's
    health a liveness dependency for the whole restore: if it died, the socket vanished and
    hive_resume.sh reported "nothing was restored" and opened zero tabs.

    The hold string is `shlex.quote`d as ONE argument. Without that, `sh -c` receives only
    `exec` and the rest becomes $0/$1, exec no-ops, the host exits immediately and takes the
    socket with it - the precise failure this refactor exists to prevent (grok review,
    2026-10-30, caught it reintroduced here).
    """
    return " ".join([
        "kitty", "-o", "allow_remote_control=yes",
        "--listen-on", shlex.quote(f"unix:{socket}"),
        "--detach", "--title", HOST_TITLE,
        "-e", "/bin/sh", "-c", shlex.quote(HOST_HOLD),
    ])


def kitty_tab_commands(state: dict, socket: str = SOCKET) -> list[str]:
    """``kitten @ launch`` for EVERY seat, the first included: one tab each, one window per group.

    No seat rides in the host any more, so no seat is special. `--env` here is what gives each
    tab its own seat - the same flag kitty refuses inside a session file.
    """
    commands = []
    opened = {state["tabs"][0]["group"]}
    target = shlex.quote(f"unix:{socket}")
    for tab in state["tabs"]:
        # The first tab of a new group opens the OS window; its siblings join it as tabs.
        kind = "tab" if tab["group"] in opened else "os-window"
        opened.add(tab["group"])
        commands.append(" ".join([
            "kitten", "@", "--to", target, "launch",
            f"--type={kind}",
            f"--title={shlex.quote(tab['name'])}",
            f"--env={shlex.quote('MEGAZWORD_SEAT=' + tab['designation'])}",
            f"--cwd={shlex.quote(tab['dir'])}",
            *[shlex.quote(part) for part in _cli_argv(tab)],
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


def _socket(socket: str | None = None) -> str:
    """The socket to talk to: the one given, else MZ_HIVE_SOCKET (single-seat restores), else ours."""
    return socket or os.environ.get("MZ_HIVE_SOCKET") or SOCKET


def seats_in_kitty(ls_dump: list) -> tuple[list[tuple[str, int | None]], list[int]]:
    """Read a ``kitty @ ls`` dump: (seat, window pid) per SEAT TAB, plus the host tab ids.

    The host is found by TITLE, never by a tab that happens to lack MEGAZWORD_SEAT. `kitty @ ls`
    reports the *process* environment, so a tab whose CLI has not appeared yet shows an empty
    env; and kitty omits variables that are identical on every window. So "no seat in this env"
    does NOT mean "no seat in this tab" - matching on it would close a real seat, and on this
    box it already would have (grok review, 2026-10-30).

    The pid is carried out because the env says what was LAUNCHED, not what is still running -
    without checking the process, a seat whose CLI died would still read as up
    (Gilberg-6969's finding, 2026-10-30).
    """
    seats: list[tuple[str, int | None]] = []
    host_tabs: list[int] = []
    for os_window in ls_dump:
        for tab in os_window.get("tabs", []):
            title = str(tab.get("title") or "")
            if title == HOST_TITLE or title.startswith(f"{HOST_TITLE} "):
                if tab.get("id") is not None:
                    host_tabs.append(tab["id"])
                continue
            for window in tab.get("windows", []):
                designation = (window.get("env") or {}).get("MEGAZWORD_SEAT")
                if designation:
                    seats.append((designation, window.get("pid")))
                    break
    return seats, host_tabs


def _alive(pid: object) -> bool:
    """Is that window's process still running? A dead CLI is not a seat that came up.

    Never os.kill(pid, 0) on Windows: signal 0 there is CTRL_C_EVENT, which sends Ctrl+C to
    the whole console - it killed the Windows CI run from inside the test suite (2026-11-02).
    """
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def kitty_ls(socket: str | None = None) -> list:
    """Ask the running kitty for its state. Empty when it is not there - never an exception.

    --all-env-vars matters: kitty drops variables that are identical on every window, which is
    exactly the inherited-seat case the seat count needs to be able to SEE.
    """
    try:
        done = subprocess.run(
            ["kitten", "@", "--to", f"unix:{_socket(socket)}", "ls", "--all-env-vars"],
            capture_output=True, text=True, timeout=20, check=True)
    except (OSError, subprocess.SubprocessError):
        return []
    try:
        return json.loads(done.stdout)
    except ValueError:
        return []


def close_host_commands(socket: str | None = None) -> list[str]:
    """Close the host tab, identified by title. Never by a missing env var."""
    _, host_tabs = seats_in_kitty(kitty_ls(socket))
    target = shlex.quote(f"unix:{_socket(socket)}")
    return [f"kitten @ --to {target} close-tab --match id:{tab_id}" for tab_id in host_tabs]


def seat_report(state: dict, socket: str | None = None) -> tuple[str, bool]:
    """``seats up: 6/6``, or what is actually wrong. False when anything is off.

    A seat counts as up only when its tab carries its own designation AND that window's process
    is still running. Counts TABS by designation rather than distinct names: two Gavins plus
    five others is still six tabs and must fail, or the count is worthless (2026-10-30 reviews).
    """
    seen, _ = seats_in_kitty(kitty_ls(socket))
    want = [tab["designation"] for tab in state["tabs"]]
    up = [(designation, pid) for designation, pid in seen if _alive(pid)]
    live = [designation for designation, _ in up]
    exited = sorted({d for d, pid in seen if not _alive(pid)})
    present = {d for d in live if d in want}
    duplicated = sorted({d for d in live if live.count(d) > 1})
    missing = [d for d in want if d not in live]
    problems = []
    if missing:
        problems.append(f"MISSING: {', '.join(missing)}")
    if duplicated:
        problems.append(f"DUPLICATED (wrong MEGAZWORD_SEAT): {', '.join(duplicated)}")
    if exited:
        problems.append(f"EXITED: {', '.join(exited)}")
    if problems:
        return (f"seats up: {len(present)}/{len(want)} - " + "; ".join(problems)), False
    return f"seats up: {len(want)}/{len(want)}", True


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
                        help="print the seatless host kitty command, and nothing else")
    parser.add_argument("--kitty-tabs", action="store_true",
                        help="print the kitten commands that open every seat, one per line")
    parser.add_argument("--ghostty", action="store_true",
                        help="print the ghostty fallback commands, one per seat")
    parser.add_argument("--close-host", action="store_true",
                        help="print close-tab commands for the seatless host tabs")
    parser.add_argument("--verify", action="store_true",
                        help="report which seats are really running; exit 1 if any are missing")
    parser.add_argument("--dir", default=WORKDIR, help="working directory for every seat")
    parser.add_argument("--only", metavar="DESIGNATION", help="include only this seat")
    args = parser.parse_args(argv)

    state = layout(args.dir, only=args.only)
    if not state["tabs"]:
        parser.error(f"unknown seat: {args.only}")

    if args.kitty_start:
        print(kitty_start_command())
        return 0
    if args.kitty_tabs:
        for command in kitty_tab_commands(state):
            print(command)
        return 0
    if args.ghostty:
        for command in ghostty_commands(state):
            print(command)
        return 0
    if args.close_host:
        for command in close_host_commands():
            print(command)
        return 0
    if args.verify:
        report, ok = seat_report(state)
        print(report)
        return 0 if ok else 1

    describe(state)
    if args.show:
        print()
        print(kitty_start_command())
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
