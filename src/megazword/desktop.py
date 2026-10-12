"""Mega Zword as a real desktop window (B6b; Phil's decision 2026-10-12: "I hate web apps").

pywebview shows the dashboard in its own native window through Windows' built-in
WebView2: no address bar, no browser tabs, the MZ icon in the title bar and taskbar.
pywebview is optional (`pip install megazword[app]`); without it Mega Zword falls
back to the Edge/Chrome `--app` window in appwindow.py.

The window needs the main thread, so the dashboard server runs in a background
thread, and closing the window stops the dashboard (it's an app now).
"""

from __future__ import annotations

import importlib.util
from importlib import resources
from pathlib import Path
from typing import Callable

TITLE = "Mega Zword"
SIZE = (1280, 860)
MIN_SIZE = (420, 560)


def available() -> bool:
    """True when pywebview is installed (it's an optional extra)."""
    try:
        return importlib.util.find_spec("webview") is not None
    except (ImportError, ValueError):
        return False


def icon_path() -> str | None:
    """The bundled MZ icon as a real file path, or None if it's missing."""
    try:
        path = Path(str(resources.files("megazword").joinpath("mz.ico")))
    except (ModuleNotFoundError, TypeError):
        return None
    return str(path) if path.is_file() else None


def run_window(url: str, on_closed: Callable[[], None] | None = None, webview=None) -> None:
    """Open the dashboard window and block until Phil closes it."""
    if webview is None:
        import webview  # type: ignore[import-not-found]
    # The plain URL, not app_url(): the native title bar already shows the MZ icon and
    # name, so the page's own app header (for browser --app windows) would repeat it.
    webview.create_window(TITLE, url, width=SIZE[0], height=SIZE[1],
                          min_size=MIN_SIZE, background_color="#0b1010",
                          text_select=True)
    options = {"private_mode": False}  # keep localStorage (chosen tab, notify prompt)
    icon = icon_path()
    if icon:  # title bar + taskbar icon (else Windows shows python's)
        options["icon"] = icon
    try:
        webview.start(**options)
    except TypeError:  # an older pywebview without some option: plain start
        webview.start()
    if on_closed:
        on_closed()


# Start menu shortcut (B6b): Mega Zword shows up in Start search with the MZ icon, and
# opens the window above. pythonw = no console window behind it.
LAUNCH_CODE = "import sys; from megazword.cli import main; sys.exit(main(['dashboard', '--app']))"


def shortcut_path(env: dict | None = None) -> Path:
    import os
    env = os.environ if env is None else env
    return (Path(env.get("APPDATA") or Path.home() / "AppData" / "Roaming")
            / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Mega Zword.lnk")


def launcher_python(python: str | None = None) -> str:
    import sys
    exe = Path(python or sys.executable)
    windowless = exe.with_name("pythonw.exe")
    return str(windowless if windowless.exists() else exe)


def shortcut_script(link: Path, target: str, args: str, icon: str | None, workdir: str) -> str:
    """PowerShell that writes the .lnk with Windows' own WScript.Shell (no new dependency).
    Values go in single-quoted strings with quotes doubled, so paths can't break out."""
    q = lambda s: "'" + str(s).replace("'", "''") + "'"
    lines = [f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({q(link)})",
             f"$s.TargetPath = {q(target)}", f"$s.Arguments = {q(args)}",
             f"$s.WorkingDirectory = {q(workdir)}", "$s.Description = 'Mega Zword'"]
    if icon:
        lines.append(f"$s.IconLocation = {q(icon + ',0')}")
    return "; ".join([*lines, "$s.Save()"])


def install_shortcut(run=None, env: dict | None = None, python: str | None = None) -> Path:
    """Create or refresh the Start menu shortcut. Windows only."""
    import subprocess
    run = run or subprocess.run
    link = shortcut_path(env)
    link.parent.mkdir(parents=True, exist_ok=True)
    args = '-c "' + LAUNCH_CODE + '"'
    script = shortcut_script(link, launcher_python(python), args, icon_path(), str(Path.home()))
    result = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                 capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise OSError((result.stderr or "could not write the shortcut").strip()[:300])
    return link


def remove_shortcut(env: dict | None = None) -> bool:
    link = shortcut_path(env)
    if link.exists():
        link.unlink()
        return True
    return False
