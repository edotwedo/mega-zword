"""Bounded fetches of public HTTPS pages for the coding agent."""
from __future__ import annotations

import http.client
import ipaddress
import re
import socket
import ssl
import threading
import time
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urljoin, urlsplit

MAX_BYTES = 256 * 1024
MAX_REDIRECTS = 3
TIMEOUT_SECONDS = 8.0
MAX_TEXT_CHARS = 20_000
_CONTENT_TYPES = {"text/plain", "text/html", "application/xhtml+xml", "application/json"}
_REDIRECTS = {301, 302, 303, 307, 308}
_DNS_SLOTS = threading.BoundedSemaphore(2)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to the validated IP while retaining hostname TLS verification."""

    def __init__(self, hostname: str, address: str, timeout: float):
        super().__init__(hostname, 443, timeout=timeout, context=ssl.create_default_context())
        self._address = address

    def connect(self):
        raw = socket.create_connection((self._address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def _resolve(host: str, timeout: float):
    if timeout <= 0 or not _DNS_SLOTS.acquire(blocking=False):
        raise ValueError("public URL DNS lookup timed out or is busy")
    done = threading.Event()
    result = {}

    def lookup():
        try:
            result["records"] = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        except OSError as exc:
            result["error"] = exc
        finally:
            _DNS_SLOTS.release()
            done.set()

    worker = threading.Thread(target=lookup, name="megazword-public-dns", daemon=True)
    try:
        worker.start()
    except RuntimeError as exc:
        _DNS_SLOTS.release()
        raise ValueError("could not start public URL DNS lookup") from exc
    if not done.wait(timeout):
        raise ValueError("public URL DNS lookup timed out")
    if "error" in result:
        raise ValueError("could not resolve public URL host") from result["error"]
    return result.get("records", [])


def _host_and_ip(hostname: str, timeout: float = TIMEOUT_SECONDS) -> tuple[str, str]:
    if not hostname or "%" in hostname:
        raise ValueError("URL host is missing or uses an unsupported address scope")
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            host = hostname.rstrip(".").encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise ValueError("URL host is invalid") from exc
        labels = host.split(".")
        if (not host or len(host) > 253 or len(labels) < 2
                or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                       for label in labels)):
            raise ValueError("URL host must be a public DNS name")
        records = _resolve(host, timeout)
        addresses = list(dict.fromkeys(record[4][0] for record in records))
        if not addresses:
            raise ValueError("public URL host has no addresses")
        parsed = []
        for address in addresses:
            if "%" in address:
                raise ValueError("public URL DNS returned a scoped address")
            try:
                parsed.append(ipaddress.ip_address(address))
            except ValueError as exc:
                raise ValueError("public URL host returned an invalid address") from exc
        if any(not address.is_global for address in parsed):
            raise ValueError("public URL host resolves to a non-public address")
        return host, addresses[0]
    if not literal.is_global:
        raise ValueError("URL host must be a public IP address")
    return hostname, str(literal)


def _target(url: str, deadline: float | None = None) -> tuple[str, str, str]:
    if not isinstance(url, str) or len(url) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in url):
        raise ValueError("URL is invalid or too long")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise ValueError("URL is malformed") from exc
    if (parts.scheme.lower() != "https" or not parts.netloc or not parts.hostname
            or parts.username is not None or parts.password is not None
            or (port is not None and port != 443)):
        raise ValueError("only credential-free HTTPS URLs on port 443 are allowed")
    for key, _ in parse_qsl(parts.query, keep_blank_values=True):
        normalized = re.sub(r"[^a-z0-9]", "", key.lower())
        if (normalized in {"token", "accesstoken", "apikey", "secret", "password", "passwd",
                           "authorization", "auth", "credential", "signature", "sig", "jwt",
                           "session", "cookie"}
                or normalized.endswith(("token", "apikey", "accesskey", "secret", "password",
                                       "credential", "signature"))):
            raise ValueError("URLs containing credential-like query parameters are not allowed")
    remaining = TIMEOUT_SECONDS if deadline is None else deadline - time.monotonic()
    host, address = _host_and_ip(parts.hostname, remaining)
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    # Keep the request line unambiguous and ASCII even for spaces or Unicode.
    from urllib.parse import quote
    path = quote(path, safe="/%:@!$&'()*+,;=-._~?%")
    return host, address, path


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style", "noscript"}:
            self.hidden += 1
        elif tag.lower() in {"br", "p", "div", "li", "h1", "h2", "h3", "tr"} and not self.hidden:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "noscript"} and self.hidden:
            self.hidden -= 1
        elif tag.lower() in {"p", "div", "li", "h1", "h2", "h3", "tr"} and not self.hidden:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def _read_body(response, connection, deadline: float) -> bytes:
    length = response.getheader("Content-Length")
    if length is not None:
        try:
            parsed_length = int(length)
        except ValueError as exc:
            raise ValueError("public page has an invalid Content-Length") from exc
        if parsed_length < 0:
            raise ValueError("public page has an invalid Content-Length")
        if parsed_length > MAX_BYTES:
            raise ValueError("public page exceeds the 256 KiB response limit")
    chunks = []
    total = 0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("public page fetch timed out")
        if connection.sock is not None:
            connection.sock.settimeout(remaining)
        try:
            chunk = response.read1(min(8192, MAX_BYTES + 1 - total))
        except (OSError, http.client.HTTPException) as exc:
            raise ValueError("could not read public page") from exc
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > MAX_BYTES:
            raise ValueError("public page exceeds the 256 KiB response limit")
    return b"".join(chunks)


def fetch_public_url(url: str) -> str:
    """Fetch a small public HTTPS text page without proxies or unsafe redirects."""
    deadline = time.monotonic() + TIMEOUT_SECONDS
    current = url
    visited = set()
    for redirect_count in range(MAX_REDIRECTS + 1):
        host, address, path = _target(current, deadline)
        if current in visited:
            raise ValueError("public page redirect loop refused")
        visited.add(current)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("public page fetch timed out")
        connection = _PinnedHTTPSConnection(host, address, remaining)
        try:
            connection.request("GET", path, headers={
                "Host": f"[{host}]" if ":" in host else host,
                "Accept": "text/html, text/plain, application/xhtml+xml, application/json",
                "User-Agent": "MegaZword-public-fetch/1.0",
                "Connection": "close",
            })
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("public page fetch timed out")
            if connection.sock is not None:
                connection.sock.settimeout(remaining)
            response = connection.getresponse()
            if response.status in _REDIRECTS:
                location = response.getheader("Location")
                if not location or redirect_count >= MAX_REDIRECTS:
                    raise ValueError("public page redirect limit reached")
                current = urljoin(current, location)
                continue
            if response.status < 200 or response.status >= 300:
                raise ValueError(f"public page returned HTTP {response.status}")
            if not response.getheader("Content-Type"):
                raise ValueError("public page did not declare a supported content type")
            content_type = response.headers.get_content_type().lower()
            if content_type not in _CONTENT_TYPES:
                raise ValueError(f"public page content type {content_type!r} is not supported")
            body = _read_body(response, connection, deadline)
            charset = response.headers.get_content_charset() or "utf-8"
            try:
                text = body.decode(charset, errors="replace")
            except LookupError:
                text = body.decode("utf-8", errors="replace")
            if content_type in {"text/html", "application/xhtml+xml"}:
                parser = _VisibleText()
                parser.feed(text)
                text = " ".join(" ".join(parser.parts).split())
            else:
                text = re.sub(r"\s+", " ", text).strip()
            if not text:
                raise ValueError("public page contained no readable text")
            return f"Fetched public page ({content_type}, {len(body)} bytes):\n{text[:MAX_TEXT_CHARS]}"
        except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
            raise ValueError("could not fetch public HTTPS page") from exc
        finally:
            connection.close()
    raise ValueError("public page redirect limit reached")
