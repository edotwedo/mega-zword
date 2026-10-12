"""Dashboard tests: no real AIs, no real meters, no real child processes."""

import json
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer

import pytest

from megazword import config, dashboard
from megazword.usage_sources import PlanUsage, Window


class FakeBackend:
    def __init__(self, ok=True):
        self.ok = ok

    def available(self):
        return self.ok


class FakeJob:
    def __init__(self, job_id, label, cmd, stdin):
        self.id, self.label, self.cmd, self.stdin = job_id, label, cmd, stdin
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def view(self):
        return {"id": self.id, "label": self.label, "out": "answer", "err": "",
                "done": True, "code": 0, "started": ""}


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    log = tmp_path / "log.jsonl"
    log.write_text(json.dumps({"time": "2026-10-11T05:00:00+00:00", "backend": "claude",
                               "ok": True, "seconds": 2.0}) + "\n")
    reset = datetime.now(timezone.utc) + timedelta(hours=2)
    usage = dashboard.Usage(lambda: [PlanUsage("claude", [Window("5-hour", 26.0, reset)], "test")])
    cfg = config.Config(log_path=log,
                        out_until={"grok": datetime.now(timezone.utc) + timedelta(days=3)})
    return dashboard.App(cfg, "proj", usage, {"claude": FakeBackend(), "grok": FakeBackend()},
                         FakeJob)


def test_state_has_meters_pace_out_and_runs(app):
    s = app.state()
    w = s["usage"][0]["windows"][0]
    assert w["used"] == 26.0 and 55 < w["elapsed"] < 65 and w["pace"] < 0
    assert "grok" in s["out"] and s["runs"][0]["backend"] == "claude"
    json.dumps(s, default=str)


def test_day_chart_counts_all_runs_not_just_recent_sixty(app):
    stamp = datetime.now(timezone.utc).isoformat()
    app.cfg.log_path.write_text("\n".join(json.dumps({
        "time": stamp, "backend": "claude", "ok": True}) for _ in range(75)))
    state = app.state()
    assert len(state["runs"]) == 60
    assert state["runs_24h"]["claude"]["runs"] == state["runs_24h"]["claude"]["ok"] == 75


def test_run_sends_prompt_on_stdin_with_project_and_model(app):
    job = app.run({"prompt": "hello there", "model": "claude", "context": True})["job"]
    j = app.jobs[job]
    assert j.stdin == "hello there"
    assert j.cmd[-6:] == ["run", "-p", "proj", "-m", "claude", "--context"]


def test_run_rejects_empty_and_unknown(app):
    with pytest.raises(ValueError):
        app.run({"prompt": "  "})
    with pytest.raises(ValueError):
        app.run({"prompt": "x", "model": "evil; rm"})


def test_note_and_decision_land_in_memory(app):
    app.note({"text": "use sonnet for setup"})
    app.note({"text": "grok out this week", "decision": True})
    kinds = [m["kind"] for m in app.state()["memory"]]
    assert kinds[:2] == ["decision", "note"]


@pytest.fixture
def server(app):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), None)
    port = srv.server_address[1]
    srv.RequestHandlerClass = dashboard.make_handler(app, port)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}", app
    srv.shutdown()
    srv.server_close()


def _post(url, body, token=None, host=None):
    req = urllib.request.Request(url, json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    if token:
        req.add_header("X-MZ-Token", token)
    if host:
        req.add_header("Host", host)
    return urllib.request.urlopen(req, timeout=5)


def test_page_carries_token_and_state_serves(server):
    base, app = server
    html = urllib.request.urlopen(base + "/", timeout=5).read().decode()
    assert app.token in html and "MEGA" in html
    state = json.loads(urllib.request.urlopen(base + "/api/state", timeout=5).read())
    assert state["project"] == "proj"


def test_post_without_token_is_refused(server):
    base, app = server
    with pytest.raises(urllib.error.HTTPError) as e:
        _post(base + "/api/run", {"prompt": "spend my usage"})
    assert e.value.code == 403 and not app.jobs


def test_foreign_host_is_refused(server):
    base, app = server
    with pytest.raises(urllib.error.HTTPError) as e:
        _post(base + "/api/run", {"prompt": "x"}, app.token, host="evil.example:80")
    assert e.value.code == 403


def test_post_with_token_starts_job(server):
    base, app = server
    job = json.loads(_post(base + "/api/run", {"prompt": "hi"}, app.token).read())["job"]
    view = json.loads(urllib.request.urlopen(f"{base}/api/job/{job}", timeout=5).read())
    assert view["done"] and view["out"] == "answer"


def test_answers_saved_trimmed_and_shown(app):
    from megazword import answers
    for i in range(5):
        answers.add(f"q{i}", f"a{i}", "claude", "proj", "easy", keep=3)
    got = answers.recent()
    assert [a["prompt"] for a in got] == ["q4", "q3", "q2"]
    assert app.state()["answers"][0]["answer"] == "a4"


def test_cancel_job(app):
    job = app.run({"prompt": "long task"})["job"]
    app.cancel({"job": job})
    assert app.jobs[job].cancelled
    with pytest.raises(ValueError):
        app.cancel({"job": "nope"})


def test_real_job_cancel_kills_process():
    import sys
    import time
    job = dashboard.Job("j1", "sleep", [sys.executable, "-c", "import time; time.sleep(30)"], "")
    job.cancel()
    for _ in range(50):
        if job.view()["done"]:
            break
        time.sleep(0.1)
    v = job.view()
    assert v["done"] and v["code"] != 0 and "cancelled" in v["err"]


@pytest.fixture
def remote_server(app):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), None)
    port = srv.server_address[1]
    srv.RequestHandlerClass = dashboard.make_handler(app, port, remote=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}", app
    srv.shutdown()
    srv.server_close()


def test_remote_needs_token_for_reads(remote_server):
    base, app = remote_server
    for path in ("/", "/api/state"):
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + path, timeout=5)
        assert e.value.code == 403


def test_remote_link_sets_cookie_and_cookie_works(remote_server):
    base, app = remote_server
    r = urllib.request.urlopen(f"{base}/?t={app.token}", timeout=5)
    cookie = r.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and app.token in cookie
    req = urllib.request.Request(base + "/api/state",
                                 headers={"Cookie": cookie.split(";")[0], "Host": "pc.tailnet:1"})
    assert json.loads(urllib.request.urlopen(req, timeout=5).read())["project"] == "proj"


def test_remote_post_still_needs_header(remote_server):
    base, app = remote_server
    with pytest.raises(urllib.error.HTTPError):
        _post(base + "/api/run", {"prompt": "x"})
    assert json.loads(_post(base + "/api/run", {"prompt": "x"}, app.token).read())["job"]


def test_serve_refuses_all_interfaces():
    assert dashboard.serve(host="0.0.0.0", open_browser=False) == 2


def test_daily_tokens_cover_full_log_not_only_recent_runs(app):
    now = datetime.now(timezone.utc)
    rows = [dict(time=now.isoformat(), backend="claude", ok=True, est_tokens=3)
            for _ in range(65)]
    rows += [dict(time=now.isoformat(), backend="grok", ok=False, prompt_chars=400),
             dict(time=(now - timedelta(days=2)).isoformat(), backend="claude",
                  ok=True, est_tokens=999)]
    app.cfg.log_path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    state = app.state()
    assert len(state["runs"]) == 60
    assert state["runs"][2]["est_tokens"] == 3
    assert state["runs_24h"]["claude"]["runs"] == 65
    assert state["runs_24h"]["claude"]["est_tokens"] == 195
    assert state["runs_24h"]["grok"]["est_tokens"] == 0


@pytest.mark.parametrize('token', [None, 'wrong'])
def test_settings_requires_token(server, token):
    base, app = server
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base + '/api/settings', {'kind': 'flag', 'name': 'quality_check', 'value': True}, token)
    assert exc.value.code == 403
    assert not (config.HOME / 'config.toml').exists()


@pytest.mark.parametrize('body', [
    {'kind': 'route', 'level': 'easy', 'names': ['codex', 'claude']},
    {'kind': 'timeout', 'ai': 'claude', 'seconds': 180},
    {'kind': 'limit', 'name': 'log_lines', 'n': 123},
    {'kind': 'flag', 'name': 'quality_check', 'value': True},
])
def test_settings_api_saves_and_exposes_values(server, body):
    base, app = server
    result = json.loads(_post(base + '/api/settings', body, app.token).read())
    assert result['ok']
    state = json.loads(urllib.request.urlopen(base + '/api/state', timeout=5).read())
    assert state['settings'] == result['settings']
    cfg = config.load()
    assert state['settings']['route'] == cfg.route
    assert state['settings']['timeouts'] == cfg.timeouts
    assert state['settings']['limits'] == {'log_lines': cfg.log_lines, 'memory_lines': cfg.memory_lines}
    assert state['settings']['quality_check'] == cfg.quality_check


@pytest.mark.parametrize('body', [[], None, {'kind': []}, {'kind': 'unknown'},
    {'kind': 'timeout', 'ai': 'claude'},
    {'kind': 'flag', 'name': 'quality_check', 'value': 'true'},
    {'kind': 'limit', 'name': 'log_lines', 'n': 0},
    {'kind': 'route', 'level': 'easy', 'names': ['bogus']}])
def test_settings_api_rejects_bad_input(server, body):
    base, app = server
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base + '/api/settings', body, app.token)
    assert exc.value.code == 400
    assert not (config.HOME / 'config.toml').exists()


def test_settings_api_disk_error_returns_json(server, monkeypatch):
    base, app = server
    def fail(*args):
        raise OSError('disk full')
    monkeypatch.setattr(config, 'set_flag', fail)
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base + '/api/settings', {'kind': 'flag', 'name': 'quality_check', 'value': True}, app.token)
    assert exc.value.code == 500
    assert json.loads(exc.value.read())['error']


@pytest.mark.parametrize("body", [[], None, 4, "prompt", {"prompt": "x", "model": ["claude"]}])
def test_bad_request_shapes_return_json_error(server, body):
    base, app = server
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base + "/api/run", body, app.token)
    assert exc.value.code == 400
    assert json.loads(exc.value.read())["error"]
    assert not app.jobs


@pytest.mark.parametrize("length, status", [("-1", 400), ("1000001", 413)])
def test_invalid_body_lengths_rejected_without_waiting(server, length, status):
    import http.client
    base, app = server
    conn = http.client.HTTPConnection(base.removeprefix("http://"), timeout=2)
    conn.request("POST", "/api/run", headers={"Content-Length": length, "X-MZ-Token": app.token})
    response = conn.getresponse()
    assert response.status == status
    response.read()
    conn.close()


def test_spawn_failure_returns_json(server):
    base, app = server
    def fail(*args):
        raise OSError("cannot spawn")
    app.launcher = fail
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base + "/api/run", {"prompt": "x"}, app.token)
    assert exc.value.code == 500
    assert json.loads(exc.value.read())["error"]


def test_remote_header_works_despite_stale_cookie(remote_server):
    base, app = remote_server
    req = urllib.request.Request(base + "/api/state", headers={
        "Cookie": "mz_t=old-launch-token", "X-MZ-Token": app.token})
    assert urllib.request.urlopen(req, timeout=5).status == 200


def test_tabs_http_list_create_rename_close_send(server, monkeypatch):
    from megazword.backends import Backend

    class RunFake(Backend):
        def _run(self, prompt: str) -> str:
            return f"ok: {prompt.splitlines()[-1][:40]}"

    base, app = server
    app.backends = {"claude": RunFake("claude"), "grok": RunFake("grok")}
    app.cfg = config.Config(log_path=config.HOME / "log.jsonl",
                            route={"easy": ["claude"], "medium": ["claude"], "hard": ["claude"]})
    listed = json.loads(urllib.request.urlopen(base + "/api/tabs", timeout=5).read())
    assert listed["tabs"] == []
    created = json.loads(_post(base + "/api/tabs",
                               {"ai": "claude", "title": "Work"}, app.token).read())
    assert created["id"] == "t1" and created["ai"] == "claude"
    renamed = json.loads(_post(base + "/api/tabs/rename",
                               {"id": "t1", "title": "Desk"}, app.token).read())
    assert renamed["title"] == "Desk"
    sent = json.loads(_post(base + "/api/tabs/send",
                            {"id": "t1", "prompt": "hello tab"}, app.token).read())
    assert sent["ok"] and sent["backend"] == "claude" and "hello tab" in sent["answer"]
    auto = json.loads(_post(base + "/api/tabs", {"ai": "auto"}, app.token).read())
    from megazword.rater import Rating
    monkeypatch.setattr("megazword.rater.rate",
                        lambda prompt, model=None: Rating("easy", "test", "fake"))
    auto_sent = json.loads(_post(base + "/api/tabs/send",
                                 {"id": auto["id"], "prompt": "auto hi"}, app.token).read())
    assert auto_sent["ok"] and auto_sent["backend"] == "claude"
    closed = json.loads(_post(base + "/api/tabs/close", {"id": "t1"}, app.token).read())
    assert closed["ok"]
    left = json.loads(urllib.request.urlopen(base + "/api/tabs", timeout=5).read())["tabs"]
    assert [t["id"] for t in left] == [auto["id"]]
    assert "tabs" in app.state()


def test_remote_malformed_cookie_returns_forbidden(remote_server):
    base, app = remote_server
    req = urllib.request.Request(base + "/api/state", headers={"Cookie": "bad@name=value"})
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=5)
    assert exc.value.code == 403


def test_answers_reject_nonpositive_retention(app):
    from megazword import answers
    with pytest.raises(ValueError, match="positive"):
        answers.add("q", "a", "fake", "proj", "easy", keep=0)


def test_done_waits_for_output_reader(monkeypatch):
    import sys
    import time
    release = threading.Event()
    waiting = threading.Event()
    pump = dashboard.Job._pump
    def delayed(stream, sink):
        waiting.set()
        release.wait(5)
        pump(stream, sink)
    monkeypatch.setattr(dashboard.Job, "_pump", staticmethod(delayed))
    job = dashboard.Job("j1", "output", [sys.executable, "-c", "print('last answer')"], "")
    try:
        assert waiting.wait(2)
        job.proc.wait(timeout=5)
        assert not job.view()["done"]
    finally:
        release.set()
    deadline = time.monotonic() + 30  # upper bound only; returns as soon as ready
    while not job.view()["done"] and time.monotonic() < deadline:
        time.sleep(.01)
    assert job.view()["done"] and job.view()["out"] == "last answer\n"


def test_running_jobs_are_never_evicted(app, monkeypatch):
    monkeypatch.setattr(dashboard, "MAX_JOBS", 2)
    first = app.run({"prompt": "running"})["job"]
    app.jobs[first].view = lambda: {"done": False}
    old = app.run({"prompt": "finished"})["job"]
    new = app.run({"prompt": "next"})["job"]
    assert first in app.jobs and old not in app.jobs and new in app.jobs
    app.jobs[new].view = lambda: {"done": False}
    with pytest.raises(ValueError, match="too many running"):
        app.run({"prompt": "excess"})
    assert len(app.jobs) == 2


def test_parallel_requests_keep_distinct_jobs(app):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = list(pool.map(lambda i: app.run({"prompt": str(i)})["job"], range(40)))
    assert len(set(jobs)) == 40 and set(jobs) == set(app.jobs)


def test_answer_writers_in_separate_processes_preserve_records(tmp_path, monkeypatch):
    import os
    import subprocess
    import sys
    from megazword import answers
    monkeypatch.setattr(config, "HOME", tmp_path)
    env = dict(os.environ, MEGAZWORD_HOME=str(tmp_path))
    code = ("import sys; from megazword import answers; "
            "[answers.add(sys.argv[1]+':'+str(i),'a','fake','proj','easy') for i in range(5)]")
    children = [subprocess.Popen([sys.executable, "-c", code, str(i)], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE) for i in range(4)]
    for child in children:
        _, err = child.communicate(timeout=20)
        assert child.returncode == 0, err.decode()
    assert len({row["prompt"] for row in answers.recent(50)}) == 20


def test_answers_skip_nonobjects(app):
    from megazword import answers
    answers.path().write_text('null\n[]\n4\n{"answer":"ok"}\n')
    assert answers.recent() == [{"answer": "ok"}]


def test_run_log_html_escapes_counts_and_accepts_string_seconds():
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed to execute dashboard rendering")
    script = dashboard.page("test").decode().split("<script>")[1].split("</script>")[0]
    script = script.split("function renderAnswers")[0]
    payload = '<img src=x onerror="alert(1)">'
    # Minimal DOM stub: top-level code also wires click/input listeners.
    program = ("const el = {addEventListener() {}}; "
               "const document = {getElementById: () => el, addEventListener() {}};\n" + script +
               "\nrenderRuns(" + json.dumps({"runs": [{"backend": "fake", "time": "2026-10-11",
                "seconds": "2.5", "prompt_chars": payload, "answer_chars": payload}]}) +
               "); console.log(el.innerHTML);")
    result = subprocess.run([node, "-e", program], capture_output=True, text=True, check=True)
    assert "<img" not in result.stdout
    assert "&lt;img" in result.stdout and "2.5" in result.stdout


def test_cancel_stops_backend_child_too(tmp_path):
    import sys
    import time
    ready = tmp_path / "ready"
    child_code = "import time; from pathlib import Path; Path(" + repr(str(ready)) + ").touch(); time.sleep(30)"
    parent_code = ("import subprocess,sys; "
                   "subprocess.run([sys.executable, '-c', " + repr(child_code) + "])")
    job = dashboard.Job("tree", "fake backend", [sys.executable, "-c", parent_code], "")
    try:
        deadline = time.monotonic() + 30  # upper bound only; returns as soon as ready
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(.02)
        assert ready.exists()
    finally:
        job.cancel()
    deadline = time.monotonic() + 30  # upper bound only; returns as soon as ready
    while not job.view()["done"] and time.monotonic() < deadline:
        time.sleep(.02)
    # The descendant inherits the pipes; they reach EOF only when it exits.
    assert job.view()["done"] and job.view()["code"] != 0
