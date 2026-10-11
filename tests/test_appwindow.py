"""App-window launch: browser discovery and the command line. No real browser."""

from megazword import appwindow
from megazword.cli import build_parser

PF, PF86, LOCAL = r"C:\Program Files", r"C:\Program Files (x86)", r"C:\Users\me\AppData\Local"
ENV = {"ProgramFiles": PF, "ProgramFiles(x86)": PF86, "LOCALAPPDATA": LOCAL}


def find(present, which=lambda n: None):
    return appwindow.find_app_browser(ENV, exists=lambda p: p in present, which=which)


def test_prefers_edge_then_chrome():
    edge = PF86 + r"\Microsoft\Edge\Application\msedge.exe"
    chrome = LOCAL + r"\Google\Chrome\Application\chrome.exe"
    assert find({edge, chrome}) == edge
    assert find({chrome}) == chrome


def test_falls_back_to_path_then_none():
    assert find(set(), which=lambda n: "/usr/bin/chromium" if n == "chromium" else None) \
        == "/usr/bin/chromium"
    assert find(set()) is None


def test_command_line():
    assert appwindow.app_command("edge.exe", "http://127.0.0.1:8765/") == \
        ["edge.exe", "--app=http://127.0.0.1:8765/", "--new-window"]


def test_open_app_launches_or_falls_back():
    launched, opened = [], []
    note = appwindow.open_app("http://x/", browser="edge.exe",
                              popen=lambda cmd, **k: launched.append(cmd), fallback=opened.append)
    assert launched == [["edge.exe", "--app=http://x/", "--new-window"]] and not opened
    assert "app window" in note

    def broken(cmd, **k):
        raise OSError("gone")
    note = appwindow.open_app("http://x/", browser="edge.exe", popen=broken,
                              fallback=opened.append)
    assert opened == ["http://x/"] and "normal browser" in note


def test_dashboard_flag_parses():
    args = build_parser().parse_args(["dashboard", "--app"])
    assert args.app and not args.no_browser


def test_favicon_is_inline_svg():
    from importlib import resources
    html = resources.files("megazword").joinpath("dashboard.html").read_text(encoding="utf-8")
    assert '<link rel="icon" href="data:image/svg+xml,' in html and "MZ" in html
