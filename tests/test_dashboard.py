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
