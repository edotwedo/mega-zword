"""Open the dashboard in its own app window (no tabs, no address bar).

Uses Edge or Chrome's `--app=<url>` mode, which every Windows PC has one of.
No new dependency: if neither is found, falls back to a normal browser tab.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import webbrowser
from pathlib import Path

# Relative to Program Files, Program Files (x86) and the user's AppData\Local.
_WINDOWS_PATHS = (
    r"Microsoft\Edge\Application\msedge.exe",
    r"Google\Chrome\Application\chrome.exe",
)
_PATH_NAMES = ("msedge", "microsoft-edge", "google-chrome", "chrome", "chromium",
               "chromium-browser")


def find_app_browser(env: dict | None = None, exists=os.path.isfile,
                     which=shutil.which) -> str | None:
    """Path to Edge or Chrome, or None. Edge first: it ships with Windows."""
    env = os.environ if env is None else env
    roots = [env.get(k) for k in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
    for rel in _WINDOWS_PATHS:
        for root in roots:
            if root:
                candidate = str(Path(root) / rel)
                if exists(candidate):
                    return candidate
    for name in _PATH_NAMES:
        if found := which(name):
            return found
    return None


def app_command(browser: str, url: str) -> list[str]:
    return [browser, f"--app={url}", "--new-window"]


def open_app(url: str, browser: str | None = None, popen=subprocess.Popen,
             fallback=webbrowser.open) -> str:
    """Open `url` as an app window. Returns a short note on what happened."""
    browser = browser or find_app_browser()
    if browser:
        try:
            popen(app_command(browser, url), stdout=subprocess.DEVNULL,
                  stderr=subprocess.DEVNULL)
            return f"opened in an app window ({Path(browser).stem})"
        except OSError:
            pass
    fallback(url)
    return "Edge/Chrome not found; opened in your normal browser"
