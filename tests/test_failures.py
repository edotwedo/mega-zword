"""Plain-English failure reasons; only usage limits mark an AI out."""

import pytest

from megazword import config
from megazword.cli import main
from megazword.failures import NetworkDown, Watch, classify
from tests.test_cli import FakeBackend, rated

CODEX_LIMIT = "ERROR: You’ve hit your usage limit. ... or try again at 2:39 AM."


@pytest.mark.parametrize("ai,error,kind,fix", [
    ("claude", "Error: Not logged in. Please run /login", "auth", "claude auth login"),
    ("codex", "401 Unauthorized: token expired", "auth", "codex login"),
    ("grok", "authentication failed", "auth", "grok login"),
    ("groq", "missing api key", "auth", "GROQ_API_KEY"),
    ("openrouter", "HTTP 403: forbidden: model is only available on agentic harnesses",
     "access", "provider allows this app"),
    ("claude", "getaddrinfo ENOTFOUND api.anthropic.com", "network", "connection"),
    ("codex", "Temporary failure in name resolution", "network", "connection"),
    ("grok", "'grok' is not installed or not on PATH", "missing", "doctor"),
    ("claude", "claude gave no answer within 600s (change ...)", "timeout", "[timeouts] claude"),
    ("codex", CODEX_LIMIT, "limit", "out codex --clear"),
])
def test_classify(ai, error, kind, fix):
    f = classify(ai, error)
    assert f.kind == kind and fix in f.fix


def test_unfamiliar_errors_are_left_alone():
    assert classify("claude", "exited with code 2: weird stack trace") is None


def test_watch_stops_after_two_network_failures_in_a_row():
    w = Watch()
    w.saw(classify("a", "ECONNREFUSED"))
    w.saw(classify("b", "not logged in"))  # resets the streak
    w.saw(classify("c", "ECONNRESET"))
    with pytest.raises(NetworkDown):
        w.saw(classify("d", "getaddrinfo failed"))


def failing(name, message):
    b = FakeBackend(name)
    b._run = lambda p: (_ for _ in ()).throw(RuntimeError(message))
    return b


@pytest.fixture
def cfg(tmp_path):
    c = config.Config(log_path=tmp_path / "log.jsonl")
    c.route = {"easy": ["a", "b", "c"], "medium": [], "hard": []}
    return c


def test_auth_failure_explained_not_marked_out(cfg, capsys):
    backends = {"a": failing("a", "Not logged in"), "b": FakeBackend("b", reply="B"),
                "c": FakeBackend("c")}
    assert main(["run", "hi"], backends, cfg, rated("easy"), dict) == 0
    err = capsys.readouterr().err
    assert "a isn't logged in" in err and "Fix: sign in to a again." in err
    assert "a" not in config.load().out_until


def test_two_network_failures_stop_the_chain(cfg, capsys):
    third = []
    c = FakeBackend("c")
    c._run = lambda p: third.append(p) or "x"
    backends = {"a": failing("a", "ENOTFOUND"), "b": failing("b", "ECONNREFUSED"), "c": c}
    assert main(["run", "hi"], backends, cfg, rated("easy"), dict) == 1
    err = capsys.readouterr().err
    assert "couldn't reach the internet" in err and "probably your connection" in err
    assert not third  # didn't keep burning through AIs
    assert not config.load().out_until  # network trouble never marks anyone out


def test_compare_explains_failures(cfg, capsys):
    backends = {"a": failing("a", "Not logged in"), "b": FakeBackend("b", reply="B")}
    assert main(["run", "hi", "--compare", "a,b"], backends, cfg, rated("easy")) == 0
    assert "a isn't logged in" in capsys.readouterr().err
