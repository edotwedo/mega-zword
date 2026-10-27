"""`megazword dashboard`: a local web page over everything megazword knows.

Shows plan meters (with pace), who's marked out, the route table, recent runs
and project memory, and has a box to run prompts. It only listens on
127.0.0.1, and every POST needs the per-launch token baked into the page, so
other websites open in the browser can't spend usage through it.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import advise, stats, answers, briefing, config, floor, room, runlog, sentinel, tabs
from .presence import CameraWatcher
from .backends import _kill_tree, default_backends, process_group
from .meters import STALE, summarize_all
from .memory import Memory, check_project, list_projects, project_name
from .run_control import Control, ENV as CONTROL_ENV

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
        self.plans: list = []  # raw PlanUsage from the last read, for meters.summarize_all

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
            self.plans = []
            return [{"service": "?", "error": str(exc), "windows": []}]
        self.plans = plans
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
            as_of = getattr(plan, "as_of", None)
            out.append({"service": plan.service, "source": plan.source, "note": plan.note,
                        "verdict": st.verdict, "burn": st.burn, "windows": windows,
                        "as_of": _iso(as_of),
                        "stale": bool(as_of and now - as_of > STALE)})
        return out


class Job:
    def __init__(self, job_id: str, label: str, cmd: list[str], stdin: str):
        self.id, self.label = job_id, label
        self.project = cmd[cmd.index('-p') + 1] if '-p' in cmd else None
        self.mode = 'review' if '--review' in cmd else 'edit' if '-e' in cmd else 'chat'
        self.started = datetime.now(timezone.utc).isoformat()
        self.out: list[str] = []
        self.err: list[str] = []
        self.code: int | None = None
        self.control = Control(config.HOME / "run-controls" / uuid.uuid4().hex) if ("-e" in cmd or '--review' in cmd) else None
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUTF8'] = '1'
        env.pop(CONTROL_ENV, None)
        env["MEGAZWORD_SEAT"] = "dashboard-" + uuid.uuid4().hex[:12]
        if self.control:
            env[CONTROL_ENV] = str(self.control.folder.resolve())
        # Own process group so cancel() also stops the AI CLI underneath.
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", env=env, **process_group())
        threading.Thread(target=self._feed, args=(stdin,), daemon=True).start()
        self._readers = [threading.Thread(target=self._pump, args=(stream, sink), daemon=True)
                         for stream, sink in ((self.proc.stdout, self.out),
                                              (self.proc.stderr, self.err))]
        for reader in self._readers:
            reader.start()
        threading.Thread(target=self._wait, daemon=True).start()

    def _feed(self, text: str) -> None:
        try:
            self.proc.stdin.write(text)
            self.proc.stdin.close()
        except OSError:
            pass

    @staticmethod
    def _pump(stream, sink: list[str]) -> None:
        with stream:
            for line in stream:
                sink.append(line)

    def _wait(self) -> None:
        code = self.proc.wait()
        # Clients stop polling at done; drain both pipes before publishing it.
        for reader in self._readers:
            reader.join()
        self.code = code

    def cancel(self) -> None:
        if self.code is None:
            try:
                if self.control:
                    self.control.request("stop")
            except (ValueError, OSError):
                pass  # Busy/unwritable control files cannot prevent cancellation.
            finally:
                self.err.append("[megazword] cancelled from the dashboard\n")
                _kill_tree(self.proc, reap=False)

    def view(self) -> dict:
        return {"id": self.id, "label": self.label, "started": self.started,
                "mode": self.mode,
                "project": getattr(self, 'project', None),
                "out": "".join(self.out), "err": "".join(self.err),
                "done": self.code is not None, "code": self.code,
                "activity": self.control.view() if self.control else None}

    def intervene(self, action, text=""):
        if not self.control or self.code is not None:
            raise ValueError("intervention needs a running free coding job")
        if self.control.view().get("phase") in ("finished", "failed"):
            raise ValueError("coding job already finished")
        self.control.request(action, text)


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
        self._job_projects: dict[str, str] = {}
        self._jobs_lock = threading.Lock()
        self._n = 0
        self._room_thread: threading.Thread | None = None
        self._room_lock = threading.RLock()
        self._room_session: tuple[str, str] | None = None  # (room, session id) started here
        from .face_identity import OwnerCamera
        self.camera = CameraWatcher(
            factory=lambda: OwnerCamera(Path.home() / ".megazword" / "workspace"))

    def briefing_view(self) -> dict:
        data = briefing.snapshot()
        return {**data, "text": briefing.render(data), "camera": self.camera.view()}

    def briefing_camera(self, body: dict) -> dict:
        enabled = body.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be true or false")
        if enabled:
            self.camera.start()
        else:
            self.camera.stop()
        return self.briefing_view()

    def project_for(self, value: object) -> str:
        """The project a request asks for (default: the launch project).
        Only safe names of existing project folders are accepted."""
        if value in (None, ""):
            return self.project
        return check_project(config.HOME, value, {self.project})

    # --- reads -----------------------------------------------------------
    def state(self, refresh: bool = False, project: object = None) -> dict:
        now = datetime.now(timezone.utc)
        project = self.project_for(project)
        # Runs logged before projects were recorded show under the launch project.
        runs = [r for r in runlog.read(self.cfg.log_path)
                if r.get("project", self.project) == project][-60:]
        memory = Memory(config.HOME, project, self.cfg.memory_lines)
        with self._jobs_lock:
            jobs = [job for job_id, job in self.jobs.items()
                    if self._job_projects.get(job_id, self.project) == project]
            busy = any(not job.view()['done'] for job in self.jobs.values())
        return {
            "now": now.isoformat(),
            "build": os.environ.get("MEGAZWORD_BUILD", "development"),
            "work_owner": self.cfg.work_owner,
            "project": project,
            "launch_project": self.project,
            "working_folder": str(Path.cwd().resolve()),
            "projects": sorted({p.name for p in list_projects(config.HOME)} | {self.project}),
            "usage": self.usage.get(force=refresh),
            # Same one-line summaries as the start screen and `megazword usage`.
            "summaries": [{"service": m.service, "state": m.state, "line": m.line()}
                          for m in summarize_all(self.usage.plans, self.cfg.out_until, now)],
            "out": {n: t.isoformat() for n, t in self.cfg.out_until.items() if t > now},
            "route": self.cfg.route,
            "settings": self.settings_state(),
            "backends": {n: b.available() for n, b in self.backends.items()},
            "runs": list(reversed(runs)),
            "trend": stats.trend(self.cfg.log_path),
            "advice": advise.as_dict(advise.advise(self.cfg)),
            "runs_24h": {name: asdict(item) for name, item in
                         runlog.summarize(self.cfg.log_path, timedelta(hours=24), now).items()},
            "memory": [asdict(e) for e in reversed(memory.recent(40))],
            "answers": answers.recent(20, project),
            "jobs": [{**j.view(), 'project': project} for j in reversed(jobs)][:10],
            "busy": busy or self.room_running(),
            "tabs": tabs.list_tabs(),
            "sentinel": sentinel.summary(),
            "floor": self.floor_state(now),
        }

    def floor_state(self, now: datetime | None = None) -> dict:
        from . import workers
        seats = floor.roster(self.backends, self.cfg.out_until, now)
        skip = floor.auth_failed(self.cfg.log_path)
        return {
            "seats": [{"name": s.name, "kind": s.kind, "status": s.status} for s in seats],
            "ready": floor.ready(seats),
            "suggest": {k: floor.suggest_seat(k, seats, skip, owner=self.cfg.work_owner)
                        for k in floor.JOB_KINDS},
            "workers": workers.roster(),
        }

    # --- actions ---------------------------------------------------------
    def settings_state(self) -> dict:
        return {"route": self.cfg.route, "timeouts": self.cfg.timeouts,
                "limits": {"log_lines": self.cfg.log_lines,
                           "memory_lines": self.cfg.memory_lines},
                "quality_check": self.cfg.quality_check,
                "ais": list(default_backends())}

    def settings(self, body: dict) -> dict:
        if not isinstance(body, dict):
            raise ValueError("settings must be an object")
        kind = body.get("kind")
        fields = {"route": ("level", "names"), "timeout": ("ai", "seconds"),
                  "limit": ("name", "n"), "flag": ("name", "value")}
        if not isinstance(kind, str) or kind not in fields:
            raise ValueError("unknown settings kind")
        if any(key not in body for key in fields[kind]):
            raise ValueError("missing settings field")
        writer = {"route": config.set_route, "timeout": config.set_timeout,
                  "limit": config.set_limit, "flag": config.set_flag}[kind]
        with config._WRITE_LOCK:
            writer(*(body[key] for key in fields[kind]))
            self.cfg = config.load()
            return {"ok": True, "settings": self.settings_state()}

    def setup_view(self) -> dict:
        """Whether this machine can run anything yet, in the dashboard.

        Setup lived only in a terminal (clone, install.ps1, init, doctor), which is
        the worst possible first five minutes for someone who just paid. This
        reports the same doctor checks the CLI prints, in one screen, with the fix
        for each gap beside it.

        Read-only: no prompt is sent and nothing is written. `can_init` is the one
        case where the panel can be useful, and it is the first thing a new
        install needs - with no config there is nothing to route with.
        """
        from . import doctor
        path = config.HOME / "config.toml"
        checks = doctor.checks()
        installed = sorted(n for n, b in self.backends.items() if b.available())
        return {
            # A bench needs something to route to, and a config that parses.
            "ready": bool(installed) and not any(c.level == "FAIL" for c in checks),
            "installed": installed,
            "can_init": not path.exists(),
            "config_path": str(path),
            "checks": [{"level": c.level, "name": c.name, "detail": c.detail, "hint": c.hint}
                       for c in checks],
        }

    def setup_init(self, body: dict) -> dict:
        """Write the starting config the setup panel offers when none exists.

        Same writer `megazword init` uses, so the two can never drift apart. On
        success the app reloads its config, so the new routes are live without a
        restart - the panel should never tell someone to restart the dashboard
        they are looking at.
        """
        installed = [n for n, b in self.backends.items() if b.available()]
        path = config.HOME / "config.toml"
        force = isinstance(body, dict) and bool(body.get("force"))
        with config._WRITE_LOCK:
            if path.exists() and not force:
                return {"error": f"config already exists: {path}", "setup": self.setup_view()}
            config.write_default(path, installed, False)
            self.cfg = config.load()
        return {"ok": True, "setup": self.setup_view()}

    def _start(self, label: str, args: list[str], stdin: str = "") -> dict:
        with self._jobs_lock:
            if len(self.jobs) >= MAX_JOBS:
                finished = next((key for key, job in self.jobs.items()
                                 if job.view()["done"]), None)
                if finished is None:
                    raise ValueError("too many running jobs; wait or cancel one")
                del self.jobs[finished]
                self._job_projects.pop(finished, None)
            self._n += 1
            job_id = f"j{self._n}"
            self.jobs[job_id] = self.launcher(job_id, label, megazword_cmd(*args), stdin)
            self._job_projects[job_id] = args[args.index('-p') + 1] if '-p' in args else self.project
        return {"job": job_id}

    def run(self, body: dict) -> dict:
        prompt = str(body.get("prompt", "")).strip()
        if not prompt:
            raise ValueError("empty prompt")
        args = ["run", "-p", self.project_for(body.get("project"))]
        from .request_mode import code_review, free_only
        reviewing = body.get('review') is True  # only when asked; no read-only by guesswork
        if reviewing:
            args.append('--review')
            if self.project_for(body.get('project')) == 'mega-zword':
                # Inspect the code the user is actually running, even when their
                # shared repository checkout is older than the installed build.
                args += ['--review-root', str(Path(__file__).resolve().parent)]
        if body.get('free_only') is True or free_only(prompt) or reviewing:
            args.append('--free-only')
        model = body.get("model") or ""
        picks = [str(n) for n in body.get("compare") or []]
        if body.get("edit"):
            if picks:
                raise ValueError("for coding, turn off compare")
            args.append("-e")
        if picks:
            if not 2 <= len(picks) <= 3 or any(n not in self.backends for n in picks):
                raise ValueError("compare needs 2 or 3 known AIs")
            args += ["--compare", ",".join(picks)]
            if body.get("context"):
                args.append("--context")
            return self._start("compare: " + prompt[:70], args, prompt)
        if model:
            if not isinstance(model, str) or model not in self.backends:
                raise ValueError(f"unknown AI {model!r}")
            args += ["-m", model]
        if body.get("context"):
            args.append("--context")
        return self._start(prompt[:80], args, prompt)

    def retry(self, body: dict) -> dict:
        args = ["retry", '-p', self.project_for(body.get("project"))]
        model = body.get("model") or ""
        if model:
            if not isinstance(model, str) or model not in self.backends:
                raise ValueError(f"unknown AI {model!r}")
            args += ["-m", model]
        return self._start("retry: " + (model or "stronger AI"), args)

    def cancel(self, body: dict) -> dict:
        job = self.jobs.get(str(body.get("job", "")))
        if job is None:
            raise ValueError("no such job")
        job.cancel()
        return {"ok": True}

    def intervene(self, body: dict) -> dict:
        with self._jobs_lock:
            job = self.jobs.get(str(body.get("job", "")))
        if job is None:
            raise ValueError("no such job")
        job.intervene(body.get("action"), body.get("text", ""))
        return {"ok": True}

    def set_out(self, body: dict) -> dict:
        """Mark an AI out (until = '7d', '2026-10-17', ...) or back (clear)."""
        name = str(body.get("ai", "")).strip()
        if name not in self.backends and name not in self.cfg.out_until:
            raise ValueError(f"unknown AI {name!r}")
        until = None if body.get("clear") else config.parse_until(str(body.get("until") or "7d"))
        config.set_out(config.HOME / "config.toml", name, until)
        self.cfg = config.load()
        return {"ok": True}

    def vote(self, body: dict) -> dict:
        """'This one's best' on a compare column."""
        ai = str(body.get("ai", "")).strip()
        if ai not in self.backends:
            raise ValueError(f"unknown AI {ai!r}")
        rating = body.get("rating")
        if rating not in (None, "", "easy", "medium", "hard"):
            raise ValueError("bad rating")
        advise.add_vote(ai, rating or None, str(body.get("prompt", "")))
        return {"ok": True}

    def note(self, body: dict) -> dict:
        text = str(body.get("text", "")).strip()
        if not text:
            raise ValueError("empty note")
        kind = "decision" if body.get("decision") else "note"
        Memory(config.HOME, self.project_for(body.get("project")),
               self.cfg.memory_lines).add(kind, text, "phil")
        return {"ok": True}

    def tabs_list(self) -> dict:
        return {"tabs": tabs.list_tabs()}

    def tabs_create(self, body: dict) -> dict:
        project = self.project_for(body.get("project") or self.project)
        return tabs.create(str(body.get("ai") or tabs.AUTO), project,
                           body.get("title"), self.backends)

    def tabs_rename(self, body: dict) -> dict:
        return tabs.rename(str(body.get("id") or ""), str(body.get("title") or ""))

    def tabs_close(self, body: dict) -> dict:
        return tabs.close(str(body.get("id") or ""))

    def tabs_new_session(self, body: dict) -> dict:
        return tabs.new_session(str(body.get("id") or ""))

    def tabs_send(self, body: dict) -> dict:
        from . import cli
        from .rater import rate
        return tabs.send(str(body.get("id") or ""), str(body.get("prompt") or ""),
                         self.backends, self.cfg,
                         lambda p: rate(p, self.cfg.rater_model),
                         cli.plan_statuses, bool(body.get("context")))

    # Hive room API for the B4 tab (Tally-11, 2026-10-12). Turns run in a background
    # thread in this process; Stop sets the room's stop flag, checked before every turn.
    def _room_name(self, value: object) -> str:
        name = str(value or self.cfg.room_name).strip()
        if not name or not all(c.isalnum() or c in "-_" for c in name):
            raise ValueError("room name may use letters, digits, - and _")
        return name

    def room_running(self) -> bool:
        return self._room_thread is not None and self._room_thread.is_alive()

    def room_view(self, name: object = None, n: int = 50) -> dict:
        from . import workers
        name = self._room_name(name)
        notices = []
        if room.remote_configured(self.cfg):
            room.show(name, n=n, cfg=self.cfg, write=notices.append)
        state = room.load_state(name)
        messages = room.read_messages(name)
        if room.remote_configured(self.cfg):
            origin = (os.environ.get("HIVE_ROOM_URL") or self.cfg.room_url).rstrip("/")
            messages = [m for m in messages if m.remote_url == origin]
        return {"room": name, "running": self.room_running(), "paused": state.paused,
                "primary": state.primary,
                "turn_count": state.turn_count, "turn_cap": state.turn_cap,
                "last_speaker": state.last_speaker,
                "messages": [asdict(m) for m in messages[-n:]],
                "notices": [line for line in notices if line.startswith("[megazword room]")],
                "workers": workers.roster()}

    def worker_send(self, body: dict) -> dict:
        from . import workers
        result = workers.send(str(body.get('target') or ''), body.get('text', ''))
        room.say(self.cfg.room_name, body['text'], author='phil → workers', write=lambda _: None, cfg=self.cfg)
        return result

    def room_say(self, body: dict) -> dict:
        name = self._room_name(body.get("room"))
        text = str(body.get("text") or "").strip()
        if not text:
            raise ValueError("empty message")
        with self._room_lock:
            if body.get("start") is True:
                turns = body.get("turns")
                if turns is not None and (type(turns) is not int or not 1 <= turns <= 50):
                    raise ValueError("turns must be 1-50")
                if body.get("project"):
                    self.project_for(body["project"])
            room.say(name, text, author="phil", write=lambda s: None, cfg=self.cfg)
            return self.room_view(name)

    def room_start(self, body: dict) -> dict:
        with self._room_lock:
            return self._start_room(body)

    def _start_room(self, body: dict) -> dict:
        raise ValueError("house bot disabled; real seats use room say/show")

    def shutdown(self) -> None:
        """The dashboard is closing: a room still running here is paused, not left 'active'."""
        self.camera.stop()
        if self.room_running() and self._room_session:
            room.release(*self._room_session)

    def room_stop(self, body: dict) -> dict:
        name = self._room_name(body.get("room"))
        room.set_stopped(name)
        return self.room_view(name)

    def room_pause(self, body: dict) -> dict:
        name = self._room_name(body.get("room"))
        room.set_paused(name)
        return self.room_view(name)


def page(token: str) -> bytes:
    html = resources.files("megazword").joinpath("dashboard.html").read_text("utf-8")
    return html.replace("__MZ_TOKEN__", token).encode("utf-8")


def make_handler(app: App, port: int, remote: bool = False):
    """remote=False: loopback only, Host header must be local, POSTs need the
    token. remote=True (e.g. over Tailscale): every request needs the token,
    from ?t=<token> once (then a cookie) or the X-MZ-Token header."""
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
            # Remote mode relies on the token instead (the Host is a Tailscale name/IP).
            return remote or self.headers.get("Host", "") in allowed_hosts

        def _given_token(self) -> str:
            query = parse_qs(urlsplit(self.path).query)
            if query.get("t"):
                return query["t"][0]
            header = self.headers.get("X-MZ-Token", "")
            if header:
                return header
            try:
                cookie = SimpleCookie(self.headers.get("Cookie", ""))
            except CookieError:
                return ""
            if "mz_t" in cookie:
                return cookie["mz_t"].value
            return self.headers.get("X-MZ-Token", "")

        def _token_ok(self, given: str) -> bool:
            return hmac.compare_digest(given.encode(), app.token.encode())

        def do_GET(self):
            if not self._host_ok():
                return self._json(403, {"error": "bad host"})
            if remote and not self._token_ok(self._given_token()):
                return self._json(403, {"error": "open the link with ?t=<token> printed by megazword"})
            path = self.path.split("?")[0]
            if path == "/":
                body = page(app.token)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                if remote:
                    self.send_header("Set-Cookie",
                                     f"mz_t={app.token}; HttpOnly; SameSite=Strict; Path=/")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/api/state":
                query = parse_qs(urlsplit(self.path).query)
                try:
                    return self._json(200, app.state(refresh=query.get("refresh") == ["1"],
                                                     project=(query.get("project") or [None])[0]))
                except ValueError as exc:
                    return self._json(400, {"error": str(exc)})
            if path == "/api/briefing":
                return self._json(200, app.briefing_view())
            if path == "/api/setup":
                return self._json(200, app.setup_view())
            if path.startswith("/api/job/"):
                job = app.jobs.get(path.rsplit("/", 1)[-1])
                return self._json(200, job.view()) if job else self._json(404, {})
            if path == "/api/tabs":
                return self._json(200, app.tabs_list())
            if path == "/api/room":
                query = parse_qs(urlsplit(self.path).query)
                try:
                    return self._json(200, app.room_view((query.get("room") or [None])[0]))
                except ValueError as exc:
                    return self._json(400, {"error": str(exc)})
            return self._json(404, {"error": "not found"})

        def do_POST(self):
            if not self._host_ok() or not self._token_ok(self.headers.get("X-MZ-Token", "")):
                return self._json(403, {"error": "bad token"})
            try:
                length = int(self.headers.get("Content-Length", 0))
                if length < 0:
                    raise ValueError("negative Content-Length")
                if length > 1_000_000:
                    return self._json(413, {"error": "request too large"})
                body = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError("request body must be a JSON object")
                action = {"/api/run": app.run, "/api/retry": app.retry,
                          "/api/note": app.note, "/api/vote": app.vote, "/api/cancel": app.cancel,
                          "/api/job/control": app.intervene,
                          "/api/settings": app.settings,
                          "/api/setup/init": app.setup_init,
                          "/api/briefing/report": briefing.publish,
                          "/api/briefing/camera": app.briefing_camera,
                          "/api/tabs": app.tabs_create,
                          "/api/tabs/rename": app.tabs_rename,
                          "/api/tabs/close": app.tabs_close,
                          "/api/tabs/send": app.tabs_send,
                          "/api/tabs/new-session": app.tabs_new_session,
                          "/api/room/say": app.room_say,
                          "/api/workers/send": app.worker_send,
                          "/api/room/start": app.room_start,
                          "/api/room/pause": app.room_pause,
                          "/api/room/stop": app.room_stop}.get(self.path)
                if action is None:
                    return self._json(404, {"error": "not found"})
                return self._json(200, action(body))
            except (ValueError, json.JSONDecodeError) as exc:
                return self._json(400, {"error": str(exc)})
            except OSError:
                return self._json(500, {"error": "could not complete the action; check local files and executable access"})

    return Handler


LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class Server(ThreadingHTTPServer):
    """One dashboard per port. HTTPServer sets SO_REUSEADDR, which on Windows lets a second
    server bind a port already in use (checked on Phil's PC, 2026-10-12): the two then answer
    at random with different tokens. Exclusive use makes the second launch fail cleanly."""
    allow_reuse_address = os.name != "nt"

    def server_bind(self):
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def running_dashboard(host: str, port: int, timeout: float = 2.0) -> bool:
    """True when a Mega Zword dashboard already answers on host:port."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/", timeout=timeout) as resp:
            return b"<title>Mega Zword</title>" in resp.read(4096)
    except (OSError, ValueError):
        return False


class AppState(App):
    """Dashboard state with the same defaults used by the server."""

    def __init__(self, cfg=None, project=None, **kwargs):
        super().__init__(cfg if cfg is not None else config.load(),
                         project if project is not None else project_name(), **kwargs)


def serve(port: int = 8765, project: str | None = None, open_browser: bool = True,
          host: str = "127.0.0.1", app_window: bool = False) -> int:
    if host in ("0.0.0.0", "::", ""):
        print("[megazword] refusing to listen on every network; pass your Tailscale IP "
              "(see `tailscale ip -4`)", file=sys.stderr)
        return 2
    remote = host not in LOOPBACK
    if open_browser and app_window and not remote:
        from .desktop import refresh_idle_dashboard
        refresh_idle_dashboard(port, os.environ.get('MEGAZWORD_BUILD', ''))
    app = AppState(project=project)
    try:
        server = Server((host, port), make_handler(app, port, remote))
    except OSError as exc:
        if not remote and running_dashboard(host, port):
            # Already open (e.g. plain `megazword` typed twice): show that one instead.
            url = f"http://{host}:{port}/"
            print(f"[megazword] the dashboard is already running at {url}", file=sys.stderr)
            if open_browser and app_window:
                from . import desktop
                if desktop.available():
                    desktop.run_window(url)  # another window onto the running one
                    return 0
                from .appwindow import open_app
                print(f"[megazword] {open_app(url)}", file=sys.stderr)
            elif open_browser:
                webbrowser.open(url)
            return 0
        print(f"[megazword] can't listen on {host}:{port}: {exc}", file=sys.stderr)
        return 1
    url = f"http://{host}:{port}/" + (f"?t={app.token}" if remote else "")
    if remote:
        print("[megazword] remote mode: anyone with this link can run your AIs. "
              "Keep it private; it changes every launch.", file=sys.stderr)
    print(f"[megazword] dashboard at {url}  (project: {app.project}; Ctrl+C to stop)",
          file=sys.stderr)
    if open_browser and app_window and not remote:
        from . import desktop
        if desktop.available():
            # B6b: a real window. It needs the main thread, so the server moves to a
            # thread, and closing the window stops the dashboard.
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                desktop.run_window(url)
            except Exception as exc:  # e.g. no WebView2 runtime: use the browser window
                server.shutdown()
                worker.join(5)
                print(f"[megazword] desktop window failed ({type(exc).__name__}: "
                      f"{str(exc)[:120]}); using a browser app window", file=sys.stderr)
            else:
                app.shutdown()
                server.shutdown()
                server.server_close()
                return 0
    if open_browser and app_window:
        from .appwindow import open_app

        def launch() -> None:
            print(f"[megazword] {open_app(url)}", file=sys.stderr)
        threading.Timer(0.5, launch).start()
    elif open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.shutdown()
        server.server_close()
    return 0
