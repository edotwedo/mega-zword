"""`megazword dashboard`: a local web page over everything megazword knows.

Shows plan meters (with pace), who's marked out, the route table, recent runs
and project memory, and has a box to run prompts. It only listens on
127.0.0.1, and every POST needs the per-launch token baked into the page, so
other websites open in the browser can't spend usage through it.
"""

from __future__ import annotations

import json
import secrets
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path

from . import answers, config, runlog
from .backends import default_backends
from .memory import Memory, project_name

USAGE_CACHE_SECONDS = 60
MAX_JOBS = 50


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class Usage:
    """Plan meters, cached so a refreshing page doesn't hammer the endpoints."""

    def __init__(self, source=None):
        self._source = source
        self._lock = threading.Lock()
        self._at = 0.0
        self._data: list[dict] = []

    def get(self, force: bool = False) -> list[dict]:
        with self._lock:
            if force or time.monotonic() - self._at > USAGE_CACHE_SECONDS or not self._at:
                self._data = self._read()
                self._at = time.monotonic()
            return self._data

    def _read(self) -> list[dict]:
        from .pacing import pace, status, window_length
        from .usage_sources import all_usage
        try:
            plans = (self._source or all_usage)()
        except Exception as exc:  # meters are best-effort
            return [{"service": "?", "error": str(exc), "windows": []}]
        now = datetime.now(timezone.utc)
        out = []
        for plan in plans:
            st = status(plan, now)
            windows = []
            for w in plan.windows:
                length, known = window_length(w.name)
                elapsed = None
                if w.resets_at is not None and known:
                    reset = w.resets_at if w.resets_at.tzinfo else \
                        w.resets_at.replace(tzinfo=timezone.utc)
                    elapsed = 100.0 * (now - (reset - length)).total_seconds() \
                        / length.total_seconds()
                    elapsed = min(100.0, max(0.0, elapsed))
                windows.append({"name": w.name, "used": float(w.used_percent),
                                "resets_at": _iso(w.resets_at), "elapsed": elapsed,
                                "known": known, "pace": pace(w, now) if known else None})
            out.append({"service": plan.service, "source": plan.source, "note": plan.note,
                        "verdict": st.verdict, "burn": st.burn, "windows": windows})
        return out


class Job:
    def __init__(self, job_id: str, label: str, cmd: list[str], stdin: str):
        self.id, self.label = job_id, label
        self.started = datetime.now(timezone.utc).isoformat()
        self.out: list[str] = []
        self.err: list[str] = []
        self.code: int | None = None
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace")
        threading.Thread(target=self._feed, args=(stdin,), daemon=True).start()
        threading.Thread(target=self._pump, args=(self.proc.stdout, self.out),
                         daemon=True).start()
        threading.Thread(target=self._pump, args=(self.proc.stderr, self.err),
                         daemon=True).start()
        threading.Thread(target=self._wait, daemon=True).start()

    def _feed(self, text: str) -> None:
        try:
            self.proc.stdin.write(text)
            self.proc.stdin.close()
        except OSError:
            pass

    @staticmethod
    def _pump(stream, sink: list[str]) -> None:
        for line in stream:
            sink.append(line)

    def _wait(self) -> None:
        self.code = self.proc.wait()

    def cancel(self) -> None:
        if self.code is None:
            self.err.append("[megazword] cancelled from the dashboard\n")
            self.proc.kill()

    def view(self) -> dict:
        return {"id": self.id, "label": self.label, "started": self.started,
                "out": "".join(self.out), "err": "".join(self.err),
                "done": self.code is not None, "code": self.code}


def megazword_cmd(*args: str) -> list[str]:
    """Run the CLI in a child process with this same Python."""
    return [sys.executable, "-c",
            "import sys; from megazword.cli import main; sys.exit(main())", *args]


class App:
    def __init__(self, cfg: config.Config, project: str, usage: Usage | None = None,
                 backends=None, launcher=Job):
        self.cfg = cfg
        self.project = project
        self.usage = usage or Usage()
        self.backends = backends if backends is not None else default_backends()
        self.launcher = launcher
        self.token = secrets.token_urlsafe(24)
        self.jobs: dict[str, Job] = {}
        self._n = 0

    # --- reads -----------------------------------------------------------
    def state(self, refresh: bool = False) -> dict:
        now = datetime.now(timezone.utc)
        runs = runlog.read(self.cfg.log_path)[-60:]
        memory = Memory(config.HOME, self.project)
        return {
            "now": now.isoformat(),
            "project": self.project,
            "usage": self.usage.get(force=refresh),
            "out": {n: t.isoformat() for n, t in self.cfg.out_until.items() if t > now},
            "route": self.cfg.route,
            "backends": {n: b.available() for n, b in self.backends.items()},
            "runs": list(reversed(runs)),
            "memory": [asdict(e) for e in reversed(memory.recent(40))],
            "answers": answers.recent(20),
            "jobs": [j.view() for j in reversed(list(self.jobs.values()))][:10],
        }

    # --- actions ---------------------------------------------------------
    def _start(self, label: str, args: list[str], stdin: str = "") -> dict:
        self._n += 1
        job_id = f"j{self._n}"
        self.jobs[job_id] = self.launcher(job_id, label, megazword_cmd(*args), stdin)
        while len(self.jobs) > MAX_JOBS:
            self.jobs.pop(next(iter(self.jobs)))
        return {"job": job_id}

    def run(self, body: dict) -> dict:
        prompt = str(body.get("prompt", "")).strip()
        if not prompt:
            raise ValueError("empty prompt")
        args = ["run", "-p", self.project]
        model = body.get("model") or ""
        if model:
            if model not in self.backends:
                raise ValueError(f"unknown AI {model!r}")
            args += ["-m", model]
        if body.get("context"):
            args.append("--context")
        return self._start(prompt[:80], args, prompt)

    def retry(self, body: dict) -> dict:
        args = ["retry"]
        model = body.get("model") or ""
        if model:
            if model not in self.backends:
                raise ValueError(f"unknown AI {model!r}")
            args += ["-m", model]
        return self._start("retry: " + (model or "stronger AI"), args)

    def cancel(self, body: dict) -> dict:
        job = self.jobs.get(str(body.get("job", "")))
        if job is None:
            raise ValueError("no such job")
        job.cancel()
        return {"ok": True}

    def note(self, body: dict) -> dict:
        text = str(body.get("text", "")).strip()
        if not text:
            raise ValueError("empty note")
        kind = "decision" if body.get("decision") else "note"
        Memory(config.HOME, self.project).add(kind, text, "phil")
        return {"ok": True}


def page(token: str) -> bytes:
    html = resources.files("megazword").joinpath("dashboard.html").read_text("utf-8")
    return html.replace("__MZ_TOKEN__", token).encode("utf-8")


def make_handler(app: App, port: int):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # keep the terminal quiet
            pass

        def _send(self, code: int, body: bytes, kind: str = "application/json") -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj) -> None:
            self._send(code, json.dumps(obj, default=str).encode("utf-8"))

        def _host_ok(self) -> bool:
            # Blocks DNS-rebinding: a page on evil.com resolving to 127.0.0.1.
            return self.headers.get("Host", "") in allowed_hosts

        def do_GET(self):
            if not self._host_ok():
                return self._json(403, {"error": "bad host"})
            path = self.path.split("?")[0]
            if path == "/":
                return self._send(200, page(app.token), "text/html; charset=utf-8")
            if path == "/api/state":
                return self._json(200, app.state(refresh="refresh=1" in self.path))
            if path.startswith("/api/job/"):
                job = app.jobs.get(path.rsplit("/", 1)[-1])
                return self._json(200, job.view()) if job else self._json(404, {})
            return self._json(404, {"error": "not found"})

        def do_POST(self):
            if not self._host_ok() or self.headers.get("X-MZ-Token") != app.token:
                return self._json(403, {"error": "bad token"})
            try:
                length = min(int(self.headers.get("Content-Length", 0)), 1_000_000)
                body = json.loads(self.rfile.read(length) or b"{}")
                action = {"/api/run": app.run, "/api/retry": app.retry,
                          "/api/note": app.note, "/api/cancel": app.cancel}.get(self.path)
                if action is None:
                    return self._json(404, {"error": "not found"})
                return self._json(200, action(body))
            except (ValueError, json.JSONDecodeError) as exc:
                return self._json(400, {"error": str(exc)})

    return Handler


def serve(port: int = 8765, project: str | None = None, open_browser: bool = True) -> int:
    app = App(config.load(), project or project_name())
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app, port))
    except OSError as exc:
        print(f"[megazword] can't listen on port {port}: {exc}", file=sys.stderr)
        return 1
    url = f"http://127.0.0.1:{port}/"
    print(f"[megazword] dashboard at {url}  (project: {app.project}; Ctrl+C to stop)",
          file=sys.stderr)
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
