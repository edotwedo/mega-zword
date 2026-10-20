"""Rename this session's terminal tab, from inside a tool shell.

Command Code sets the tab title itself (session name plus model) through the
console, so a bot that runs in a hidden console cannot see or change the tab
Phil is looking at. This works around it: walk up the process tree to the shell
that Windows Terminal is hosting for this tab, attach to that console, and set
its title. Because Command Code keeps re-asserting its own title, a short keeper
process re-applies the wanted name until the tab closes.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

from . import config

ATTACH_PARENT_PROCESS = 0xFFFFFFFF
STD_OUTPUT_HANDLE = -11
STD_ERROR_HANDLE = -12
DEFAULT_INTERVAL = 1.0
TERMINAL_NAMES = ("windowsterminal.exe",)


def state_path() -> Path:
    return config.HOME / "tab_title.json"


def _k32():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.FreeConsole.argtypes = []
    k.FreeConsole.restype = wintypes.BOOL
    k.AttachConsole.argtypes = [wintypes.DWORD]
    k.AttachConsole.restype = wintypes.BOOL
    k.SetConsoleTitleW.argtypes = [wintypes.LPCWSTR]
    k.SetConsoleTitleW.restype = wintypes.BOOL
    k.GetConsoleTitleW.argtypes = [wintypes.LPWSTR, wintypes.DWORD]
    k.GetConsoleTitleW.restype = wintypes.DWORD
    k.GetStdHandle.argtypes = [wintypes.DWORD]
    k.GetStdHandle.restype = wintypes.HANDLE
    k.SetStdHandle.argtypes = [wintypes.DWORD, wintypes.HANDLE]
    k.SetStdHandle.restype = wintypes.BOOL
    return k


def tab_pid(process=None) -> int:
    """The shell Windows Terminal hosts for this tab, or 0 for "attach to parent".

    The bot runs several levels below that shell (tool shell, then the CLI), so
    AttachConsole(ATTACH_PARENT_PROCESS) lands on a hidden console, not the tab.
    """
    if os.name != "nt":
        return 0
    if process is None:
        try:
            import psutil
            process = psutil.Process()
        except Exception:
            return 0
    for _ in range(32):
        try:
            parent = process.parent()
        except Exception:
            return 0
        if parent is None:
            return 0
        try:
            name = (parent.name() or "").lower()
        except Exception:
            name = ""
        if name in TERMINAL_NAMES:
            return process.pid
        process = parent
    return 0


def _save_std() -> dict:
    """AttachConsole repoints our std handles at the new console, which would
    swallow output the caller is capturing. Save them so we can put them back."""
    if os.name != "nt":
        return {}
    k = _k32()
    return {slot: k.GetStdHandle(code)
            for slot, code in (("out", STD_OUTPUT_HANDLE), ("err", STD_ERROR_HANDLE))}


def _restore_std(saved: dict) -> None:
    if os.name != "nt" or not saved:
        return
    k = _k32()
    for slot, code in (("out", STD_OUTPUT_HANDLE), ("err", STD_ERROR_HANDLE)):
        if slot in saved:
            k.SetStdHandle(code, saved[slot])


def _attach(pid: int) -> bool:
    if os.name != "nt":
        return False
    k = _k32()
    k.FreeConsole()
    target = ATTACH_PARENT_PROCESS if not pid else int(pid)
    return bool(k.AttachConsole(target))


def _set_title(title: str) -> bool:
    if os.name != "nt":
        return False
    return bool(_k32().SetConsoleTitleW(title))


def read_title(pid: int = 0) -> str:
    if os.name != "nt":
        return ""
    k = _k32()
    buf = ctypes.create_unicode_buffer(512)
    if not k.GetConsoleTitleW(buf, 512):
        return ""
    return buf.value


def apply_title(title: str, pid: int = 0) -> bool:
    """Attach to the tab console, set the title once, restore our std handles."""
    saved = _save_std()
    try:
        if not _attach(pid):
            return False
        return _set_title(title)
    finally:
        _restore_std(saved)


def read_tab_title(pid: int = 0) -> str:
    """The tab console's title, which needs the same attach as setting it."""
    saved = _save_std()
    try:
        if not _attach(pid):
            return ""
        return read_title(pid)
    finally:
        _restore_std(saved)


def read_state() -> dict:
    try:
        data = json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_state(**fields) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fields, indent=2), encoding="utf-8")


def keeper_alive() -> bool:
    pid = read_state().get("keeper_pid")
    if not pid:
        return False
    try:
        import psutil
        return psutil.pid_exists(int(pid))
    except Exception:
        return False


def keep(title: str, tab: int, interval: float = DEFAULT_INTERVAL,
         attach=None, setter=None, alive=None, sleep=time.sleep, stop=None) -> int:
    """Hold the title: Command Code keeps re-writing its own, so re-assert ours."""
    if alive is None:
        def alive(pid):
            try:
                import psutil
                return psutil.pid_exists(int(pid))
            except Exception:
                return False
    if stop is None:
        stop = lambda: bool(read_state().get("stop"))  # noqa: E731
    if attach is None:
        attach = _attach
    if setter is None:
        setter = _set_title
    saved = _save_std()
    try:
        if not attach(tab):
            return 1
        while alive(tab) and not stop():
            setter(title)
            sleep(interval)
    finally:
        _restore_std(saved)
    return 0


def _spawn_keeper(title: str, tab: int, interval: float) -> int:
    cmd = [sys.executable, "-m", "megazword.tab_title",
           "--keep", title, "--tab-pid", str(tab), "--interval", str(interval)]
    flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=flags, close_fds=True)
    return proc.pid


def stop_keeper() -> bool:
    state = read_state()
    pid = state.get("keeper_pid")
    write_state(**{**state, "stop": True})
    if not pid:
        return False
    try:
        import psutil
        proc = psutil.Process(int(pid))
        proc.terminate()
        proc.wait(timeout=3)
        return True
    except Exception:
        return False


def command(args) -> int:
    if args.stop:
        stopped = stop_keeper()
        print("keeper stopped" if stopped else "no keeper to stop")
        return 0
    state = read_state()
    if not args.title:
        tab = tab_pid()
        print(f"tab shell pid: {tab or 'unknown'}")
        print(f"current title: {read_tab_title(tab) or '(unreadable)'}")
        print(f"wanted title: {state.get('title') or '(none set)'}")
        print(f"keeper: {'running (pid %s)' % state.get('keeper_pid') if keeper_alive() else 'not running'}")
        return 0
    tab = tab_pid()
    print(f"tab shell pid: {tab or 'unknown (attaching to parent)'}")
    if not apply_title(args.title, tab):
        print("could not reach this tab's console; leaving the title alone")
        return 1
    if args.once:
        write_state(title=args.title, tab_pid=tab, keeper_pid=None, stop=False,
                    seat=os.environ.get("MEGAZWORD_SEAT", ""))
        print(f"tab title set to {args.title} (once; Command Code may reset it)")
        return 0
    if keeper_alive() and state.get("title") == args.title:
        print(f"tab title is {args.title}; keeper already running (pid {state['keeper_pid']})")
        return 0
    stop_keeper()
    keeper = _spawn_keeper(args.title, tab, args.interval)
    write_state(title=args.title, tab_pid=tab, keeper_pid=keeper, stop=False,
                seat=os.environ.get("MEGAZWORD_SEAT", ""))
    print(f"tab title set to {args.title}; keeper pid {keeper} holds it while this tab lives")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("title", nargs="?", help="the tab title, usually your designation")
    parser.add_argument("--stop", action="store_true", help="stop the keeper")
    parser.add_argument("--once", action="store_true", help="set the title once, no keeper")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL,
                        help="keeper re-apply seconds (default: 1.0)")
    parser.add_argument("--keep", help="internal: hold this title (used by the keeper)")
    parser.add_argument("--tab-pid", type=int, default=0, help="internal: tab shell pid")
    args = parser.parse_args(argv)
    if args.keep is not None:
        return keep(args.keep, args.tab_pid, args.interval)
    return command(args)


def add_parser(sub) -> None:
    tab = sub.add_parser("tab", help="rename this terminal tab")
    tab.add_argument("title", nargs="?", help="the tab title, usually your designation")
    tab.add_argument("--stop", action="store_true", help="stop the keeper")
    tab.add_argument("--once", action="store_true", help="set the title once, no keeper")
    tab.add_argument("--interval", type=float, default=DEFAULT_INTERVAL,
                     help="keeper re-apply seconds (default: 1.0)")


if __name__ == "__main__":
    raise SystemExit(main())
