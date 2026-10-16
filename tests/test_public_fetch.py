from email.message import Message

import pytest

from megazword import public_fetch


@pytest.mark.parametrize("url", [
    "http://example.com/", "https://user:pass@example.com/", "https://example.com:8443/",
    "https://127.0.0.1/", "https://[::1]/", "https://localhost/", "https://example.com/a\nB",
    "https://example.com/docs?api_key=private-value", "https://example.com/docs?access_token=x",
])
def test_target_rejects_unsafe_urls(url):
    with pytest.raises(ValueError):
        public_fetch._target(url)


def test_target_quotes_request_line_spaces(monkeypatch):
    monkeypatch.setattr(public_fetch, "_host_and_ip", lambda host, timeout=8: (host, "93.184.216.34"))
    assert public_fetch._target("https://example.com/a b") == (
        "example.com", "93.184.216.34", "/a%20b")


def test_dns_rejects_any_non_public_answer(monkeypatch):
    monkeypatch.setattr(public_fetch.socket, "getaddrinfo", lambda *a, **k: [
        (2, 1, 6, "", ("93.184.216.34", 443)),
        (2, 1, 6, "", ("10.0.0.8", 443)),
    ])
    with pytest.raises(ValueError, match="non-public"):
        public_fetch._host_and_ip("example.com")


def test_pinned_connection_uses_validated_ip_and_original_tls_name(monkeypatch):
    observed = {}

    class FakeSocket:
        def close(self):
            observed["closed"] = True

    class FakeContext:
        def wrap_socket(self, sock, server_hostname):
            observed["server_hostname"] = server_hostname
            return sock

    def connect(address, timeout):
        observed.update(address=address[0], port=address[1], timeout=timeout)
        return FakeSocket()

    monkeypatch.setattr(public_fetch.socket, "create_connection", connect)
    connection = public_fetch._PinnedHTTPSConnection("docs.example", "93.184.216.34", 3)
    connection._context = FakeContext()
    connection.connect()
    assert observed["address"] == "93.184.216.34"
    assert observed["port"] == 443
    assert observed["server_hostname"] == "docs.example"
    connection.close()


class FakeResponse:
    def __init__(self, status=200, body=b"<p>Visible</p><script>secret()</script>", headers=None):
        self.status = status
        self.headers = Message()
        for name, value in (headers or {"Content-Type": "text/html; charset=utf-8"}).items():
            self.headers[name] = value
        self.body = body

    def getheader(self, name):
        return self.headers.get(name)

    def read1(self, size):
        data, self.body = self.body[:size], self.body[size:]
        return data


def test_fetch_strips_script_text_and_uses_pinned_connection(monkeypatch):
    seen = {}

    class FakeConnection:
        def __init__(self, host, address, timeout):
            seen["connection"] = (host, address, timeout)
            self.sock = None

        def request(self, method, path, headers):
            seen["request"] = (method, path, headers)

        def getresponse(self):
            return FakeResponse()

        def close(self):
            pass

    monkeypatch.setattr(public_fetch, "_host_and_ip", lambda host, timeout=8: (host, "93.184.216.34"))
    monkeypatch.setattr(public_fetch, "_PinnedHTTPSConnection", FakeConnection)
    result = public_fetch.fetch_public_url("https://example.com/docs")
    assert "Visible" in result
    assert "secret" not in result
    assert seen["connection"][:2] == ("example.com", "93.184.216.34")
    assert seen["request"][0:2] == ("GET", "/docs")


def test_fetch_revalidates_redirect_destination(monkeypatch):
    calls = []
    resolve = public_fetch._host_and_ip

    class FakeConnection:
        def __init__(self, host, address, timeout):
            calls.append(host)
            self.sock = None

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return FakeResponse(302, b"", {"Location": "https://127.0.0.1/private"})

        def close(self):
            pass

    monkeypatch.setattr(public_fetch, "_host_and_ip", lambda host, timeout=8: (
        (host, "93.184.216.34") if host == "example.com" else resolve(host, timeout)))
    monkeypatch.setattr(public_fetch, "_PinnedHTTPSConnection", FakeConnection)
    with pytest.raises(ValueError, match="public IP"):
        public_fetch.fetch_public_url("https://example.com/start")
    assert calls == ["example.com"]


def test_fetch_rejects_oversized_response_before_reading(monkeypatch):
    class FakeConnection:
        def __init__(self, *args):
            self.sock = None

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return FakeResponse(headers={"Content-Type": "text/plain",
                                         "Content-Length": str(public_fetch.MAX_BYTES + 1)})

        def close(self):
            pass

    monkeypatch.setattr(public_fetch, "_host_and_ip", lambda host, timeout=8: (host, "93.184.216.34"))
    monkeypatch.setattr(public_fetch, "_PinnedHTTPSConnection", FakeConnection)
    with pytest.raises(ValueError, match="256 KiB"):
        public_fetch.fetch_public_url("https://example.com/large")


def test_fetch_caps_stream_without_content_length(monkeypatch):
    class FakeConnection:
        def __init__(self, *args):
            self.sock = None

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return FakeResponse(body=b"x" * (public_fetch.MAX_BYTES + 1),
                                headers={"Content-Type": "text/plain"})

        def close(self):
            pass

    monkeypatch.setattr(public_fetch, "_host_and_ip", lambda host, timeout=8: (host, "93.184.216.34"))
    monkeypatch.setattr(public_fetch, "_PinnedHTTPSConnection", FakeConnection)
    with pytest.raises(ValueError, match="256 KiB"):
        public_fetch.fetch_public_url("https://example.com/stream")
