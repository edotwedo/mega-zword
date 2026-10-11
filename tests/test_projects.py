"""Projects: listing, the dashboard switcher, and no escaping the folder."""

import json
import urllib.error
import urllib.request

import pytest

from megazword import answers, config
from megazword.cli import main
from megazword.memory import Memory, check_project, list_projects
from tests.test_cli import FakeBackend


def make(name, *entries):
    mem = Memory(config.HOME, name)
    for kind, text in entries:
        mem.add(kind, text)
    return mem


def test_list_projects_counts_and_orders():
    make("alpha", ("decision", "rule"), ("note", "n1"))
    make("beta", ("note", "n"))
    (config.HOME / "projects" / "..weird").mkdir(parents=True)  # unsafe name: ignored
    found = {p.name: p for p in list_projects(config.HOME)}
    assert set(found) == {"alpha", "beta"}
    assert (found["alpha"].entries, found["alpha"].decisions) == (2, 1)
    assert found["beta"].last


def test_cli_projects(capsys):
    assert main(["projects"], {}) == 0
    assert "no projects yet" in capsys.readouterr().out
    make("alpha", ("decision", "rule"))
    assert main(["projects"], {}) == 0
    assert "alpha" in capsys.readouterr().out


@pytest.mark.parametrize("bad", ["..", "../alpha", r"..\alpha", "a/b", r"a\b", "C:", r"C:\x",
                                 "/etc", ".hidden", "", "x" * 65, None, 5, ["alpha"],
                                 "alpha\x00", "alpha\n"])
def test_unsafe_names_are_rejected(bad):
    make("alpha", ("note", "n"))
    with pytest.raises(ValueError):
        check_project(config.HOME, bad)


def test_missing_project_rejected_unless_allowed():
    with pytest.raises(ValueError):
        check_project(config.HOME, "ghost")
    assert check_project(config.HOME, "ghost", {"ghost"}) == "ghost"


@pytest.fixture
def app(tmp_path):
    from megazword.dashboard import App
    started = []
    a = App(config.Config(log_path=tmp_path / "log.jsonl"), "home",
            backends={"claude": FakeBackend("claude")},
            launcher=lambda *args: started.append(args) or type("J", (), {"view": lambda s: {}})())
    a.started = started
    return a


def test_state_follows_selected_project(app):
    make("alpha", ("note", "alpha note"))
    make("home", ("note", "home note"))
    answers.add("q-alpha", "a", "claude", "alpha", None)
    answers.add("q-home", "a", "claude", "home", None)
    app.cfg.log_path.write_text("\n".join(json.dumps(r) for r in [
        {"time": "2026-10-11T00:00:00+00:00", "backend": "claude", "ok": True, "project": "alpha"},
        {"time": "2026-10-11T00:00:00+00:00", "backend": "claude", "ok": True},  # old: launch
    ]) + "\n", encoding="utf-8")
    s = app.state(project="alpha")
    assert s["project"] == "alpha" and "alpha" in s["projects"] and "home" in s["projects"]
    assert [m["text"] for m in s["memory"]] == ["alpha note"]
    assert [a["prompt"] for a in s["answers"]] == ["q-alpha"] and len(s["runs"]) == 1
    home = app.state()
    assert home["project"] == "home" and [m["text"] for m in home["memory"]] == ["home note"]
    assert [a["prompt"] for a in home["answers"]] == ["q-home"] and len(home["runs"]) == 1


def test_actions_use_project_and_reject_traversal(app):
    make("alpha", ("note", "x"))
    app.run({"prompt": "hi", "project": "alpha"})
    assert app.started[-1][2][app.started[-1][2].index("-p") + 1] == "alpha"
    app.note({"text": "for alpha", "project": "alpha"})
    assert Memory(config.HOME, "alpha").recent(1)[0].text == "for alpha"
    for body in ({"prompt": "hi", "project": "../alpha"}, {"text": "t", "project": r"..\x"}):
        with pytest.raises(ValueError):
            (app.run if "prompt" in body else app.note)(body)
    assert not (config.HOME / "x").exists()


def test_http_state_rejects_bad_project(app):
    import threading
    from http.server import ThreadingHTTPServer
    from megazword.dashboard import make_handler
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app, 0))
    port = server.server_address[1]
    server.RequestHandlerClass = make_handler(app, port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{port}/api/state?project=..%2F..%2Fetc"
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(url, timeout=10)
        assert exc.value.code == 400
        ok = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=10).read())
        assert ok["project"] == "home"
    finally:
        server.shutdown()
