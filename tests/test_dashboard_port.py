"""One dashboard per port, and a second launch reuses the running one."""

import socket
import threading

from megazword import config, dashboard


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_second_server_cannot_share_the_port():
    port = free_port()
    first = dashboard.Server(("127.0.0.1", port), dashboard.BaseHTTPRequestHandler)
    try:
        try:
            second = dashboard.Server(("127.0.0.1", port), dashboard.BaseHTTPRequestHandler)
        except OSError:
            second = None
        assert second is None, "a second dashboard bound the same port"
    finally:
        first.server_close()


def test_second_launch_opens_the_running_dashboard(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    port = free_port()
    app = dashboard.App(config.Config(log_path=tmp_path / "log.jsonl"), "proj", None, {})
    server = dashboard.Server(("127.0.0.1", port), dashboard.make_handler(app, port))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    opened = []
    monkeypatch.setattr("megazword.appwindow.open_app", lambda url: opened.append(url) or "ok")
    try:
        assert dashboard.running_dashboard("127.0.0.1", port)
        assert dashboard.serve(port, open_browser=True, app_window=True) == 0
        assert opened == [f"http://127.0.0.1:{port}/"]
    finally:
        server.shutdown()
        server.server_close()


def test_nothing_listening_is_not_a_dashboard():
    assert not dashboard.running_dashboard("127.0.0.1", free_port(), timeout=0.5)
