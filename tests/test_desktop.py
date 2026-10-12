"""B6b desktop window: pywebview is faked, so no real window ever opens."""

import struct
import urllib.request

from megazword import config, dashboard, desktop

from test_dashboard_port import free_port


class FakeWebview:
    def __init__(self, on_start=None, old=False):
        self.windows, self.started, self.on_start, self.old = [], [], on_start, old

    def create_window(self, title, url, **kw):
        self.windows.append((title, url, kw))

    def start(self, **options):
        if self.old and options:
            raise TypeError("unexpected keyword")
        self.started.append(options)
        if self.on_start:
            self.on_start()


def test_window_has_title_app_url_size_and_icon():
    web = FakeWebview()
    closed = []
    desktop.run_window("http://127.0.0.1:8765/#hive", on_closed=lambda: closed.append(1),
                       webview=web)
    title, url, kw = web.windows[0]
    assert title == "Mega Zword"
    assert url == "http://127.0.0.1:8765/#hive"  # no ?app=1: the native title bar has the icon
    assert (kw["width"], kw["height"]) == desktop.SIZE and kw["min_size"] == desktop.MIN_SIZE
    assert web.started[0]["private_mode"] is False
    assert web.started[0]["icon"].endswith("mz.ico")
    assert closed == [1]


def test_older_pywebview_still_starts():
    web = FakeWebview(old=True)
    desktop.run_window("http://x/", webview=web)
    assert web.started == [{}]


def test_icon_is_a_multi_size_ico():
    data = open(desktop.icon_path(), "rb").read()
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    assert (reserved, kind) == (0, 1) and count >= 4
    sizes = {data[6 + 16 * i] or 256 for i in range(count)}
    assert {16, 32, 48, 256} <= sizes


def test_serve_runs_the_server_while_the_window_is_open(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(dashboard.config, "load",
                        lambda: config.Config(log_path=tmp_path / "log.jsonl"))
    port = free_port()
    seen = []

    def fake_window(url, on_closed=None):
        # While the "window" is open the dashboard answers; closing returns.
        with urllib.request.urlopen(url, timeout=5) as resp:
            seen.append((url, b"<title>Mega Zword</title>" in resp.read(4096)))

    monkeypatch.setattr(desktop, "available", lambda: True)
    monkeypatch.setattr(desktop, "run_window", fake_window)
    assert dashboard.serve(port, project="proj", open_browser=True, app_window=True) == 0
    assert seen == [(f"http://127.0.0.1:{port}/", True)]
    # Closing the window stopped the server: the port is free again.
    assert not dashboard.running_dashboard("127.0.0.1", port, timeout=0.5)


def test_second_launch_opens_a_window_onto_the_running_dashboard(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    port = free_port()
    app = dashboard.App(config.Config(log_path=tmp_path / "log.jsonl"), "proj", None, {})
    server = dashboard.Server(("127.0.0.1", port), dashboard.make_handler(app, port))
    import threading
    threading.Thread(target=server.serve_forever, daemon=True).start()
    windows = []
    monkeypatch.setattr(desktop, "available", lambda: True)
    monkeypatch.setattr(desktop, "run_window", lambda url: windows.append(url))
    try:
        # Second launch with pywebview: a new window onto the running dashboard.
        assert dashboard.serve(port, open_browser=True, app_window=True) == 0
        assert windows == [f"http://127.0.0.1:{port}/"]
    finally:
        server.shutdown()
        server.server_close()


def test_shortcut_goes_in_the_users_start_menu(tmp_path):
    link = desktop.shortcut_path({"APPDATA": str(tmp_path)})
    assert link == tmp_path / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Mega Zword.lnk"


def test_shortcut_script_quotes_paths_safely():
    script = desktop.shortcut_script(r"C:\Users\o'neil\Mega Zword.lnk", r"C:\py\pythonw.exe",
                                     '-c "x"', r"C:\a\mz.ico", r"C:\Users\o'neil")
    assert r"CreateShortcut('C:\Users\o''neil\Mega Zword.lnk')" in script
    assert "$s.Arguments = '-c \"x\"'" in script
    assert r"$s.IconLocation = 'C:\a\mz.ico,0'" in script
    assert script.endswith("$s.Save()")


def test_install_and_remove_shortcut(tmp_path):
    calls = []

    class Done:
        returncode, stderr = 0, ""

    def fake_run(cmd, **kw):
        calls.append(cmd)
        desktop.shortcut_path({"APPDATA": str(tmp_path)}).write_text("lnk")
        return Done()

    link = desktop.install_shortcut(run=fake_run, env={"APPDATA": str(tmp_path)})
    assert link.exists() and calls[0][:3] == ["powershell", "-NoProfile", "-NonInteractive"]
    script = calls[0][-1]
    assert "pythonw" in script.lower() or "python" in script.lower()
    # Single quotes are doubled inside the PowerShell string.
    assert "main([''dashboard'', ''--app''])" in script and "mz.ico,0" in script
    assert desktop.remove_shortcut({"APPDATA": str(tmp_path)}) is True
    assert desktop.remove_shortcut({"APPDATA": str(tmp_path)}) is False


def test_failed_shortcut_raises(tmp_path):
    class Failed:
        returncode, stderr = 1, "access denied"
    import pytest
    with pytest.raises(OSError, match="access denied"):
        desktop.install_shortcut(run=lambda cmd, **kw: Failed(), env={"APPDATA": str(tmp_path)})
