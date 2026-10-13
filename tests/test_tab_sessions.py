"""Session CLI wire formats and dashboard persistence, without AI calls."""

import json
from pathlib import Path
import uuid

import pytest

from megazword import tabs
from megazword.backends import CLIBackend, default_backends
from megazword.tab_sessions import session_missing
from test_tabs import Capture, cfg, rate


@pytest.fixture
def fake_cli(monkeypatch):
    calls = []
    failures = []
    monkeypatch.setattr("megazword.backends.shutil.which", lambda exe: exe)

    def execute(cli, cmd, stdin):
        prompt = stdin
        if "--prompt-file" in cmd:
            prompt = Path(cmd[cmd.index("--prompt-file") + 1]).read_text(encoding="utf-8")
        calls.append((cli.exe, cmd, prompt))
        if failures:
            error = failures.pop(0)
            if error:
                raise RuntimeError(error)
        if cli.exe == "claude":
            session = cmd[cmd.index("--resume") + 1] if "--resume" in cmd else str(uuid.uuid4())
            return json.dumps({"result": "Useful answer", "session_id": session, "is_error": False})
        if cli.exe == "codex":
            session = cmd[cmd.index("resume") + 1] if "resume" in cmd else str(uuid.uuid4())
            Path(cmd[cmd.index("-o") + 1]).write_text("Useful answer", encoding="utf-8")
            return json.dumps({"type": "thread.started", "thread_id": session}) + "\n"
        return "Useful answer"

    monkeypatch.setattr(CLIBackend, "_exec", execute)
    return calls, failures


@pytest.mark.parametrize("name", ["claude", "codex", "grok"])
def test_persist_resume_and_reset(name, fake_cli):
    calls, _ = fake_cli
    bs = default_backends(free_models={})
    tab = tabs.create(name, "alpha", backends=bs)
    original_args = list(bs[name].args)
    first = tabs.send(tab["id"], "Remember apples", bs, cfg(), rate(), statuses=dict)
    assert first["ok"]
    session = first["tab"]["session_id"]
    uuid.UUID(session)
    # Reload from disk and construct fresh backend objects, like an app restart.
    assert tabs.list_tabs()[0]["session_id"] == session
    second = tabs.send(tab["id"], "What fruit?", default_backends(free_models={}),
                       cfg(), rate(), statuses=dict, context=True)
    assert second["ok"] and second["tab"]["session_id"] == session
    assert calls[1][2] == "What fruit?"  # no history, context, or one-shot note
    resume_flag = "resume" if name == "codex" else "--resume"
    assert calls[1][1][calls[1][1].index(resume_flag) + 1] == session
    assert bs[name].args == original_args
    if name == "codex":
        cmd = calls[1][1]
        assert cmd.index("-s") < cmd.index("resume")
        assert cmd[cmd.index("-s") + 1] == "read-only"
        assert "--json" in cmd and "mcp_servers={}" in cmd
    if name == "claude":
        assert calls[1][1][calls[1][1].index("--output-format") + 1] == "json"
        assert "--restricted" in calls[1][1]
    reset = tabs.new_session(tab["id"])
    assert not reset["session_id"] and reset["history"] == []
    fresh = tabs.send(tab["id"], "Start over", bs, cfg(), rate(), statuses=dict)
    assert fresh["ok"] and fresh["tab"]["session_id"] != session
    assert resume_flag not in calls[-1][1]
    assert "Remember apples" not in calls[-1][2]


@pytest.mark.parametrize("name", ["claude", "codex", "grok"])
def test_missing_session_retries_once_with_history(name, fake_cli):
    calls, failures = fake_cli
    bs = default_backends(free_models={})
    tab = tabs.create(name, "alpha", backends=bs)
    first = tabs.send(tab["id"], "Remember apples", bs, cfg(), rate(), statuses=dict)
    failures.extend(["Session not found", None])
    second = tabs.send(tab["id"], "What fruit?", bs, cfg(), rate(), statuses=dict)
    assert second["ok"] and len(calls) == 3
    assert second["tab"]["session_id"] != first["tab"]["session_id"]
    assert "started a new session" in second["tab"]["session_note"]
    assert calls[1][2] == "What fruit?"
    assert "User: Remember apples" in calls[2][2]


@pytest.mark.parametrize("error,attempts", [("Session expired", 2), ("Authentication failed", 1),
                                         ("rate limit exceeded", 1), ("network unreachable", 1)])
def test_failure_does_not_loop_or_retry_other_errors(error, attempts, fake_cli):
    calls, failures = fake_cli
    bs = default_backends(free_models={})
    tab = tabs.create("claude", "alpha", backends=bs)
    first = tabs.send(tab["id"], "hello", bs, cfg(), rate(), statuses=dict)
    failures.extend([error] * attempts)
    result = tabs.send(tab["id"], "next", bs, cfg(), rate(), statuses=dict)
    assert not result["ok"] and len(calls) == 1 + attempts
    assert tabs.list_tabs()[0]["history"] == first["tab"]["history"]


def test_auto_switch_and_escalation_track_actual_backend(fake_cli):
    calls, failures = fake_cli
    bs = default_backends(free_models={})
    tab = tabs.create("auto", "alpha", backends=bs)
    settings = cfg(route={"easy": ["claude", "codex"], "hard": ["grok"]})
    first = tabs.send(tab["id"], "hello", bs, settings, rate(), statuses=dict)
    failures.append("network unreachable")
    second = tabs.send(tab["id"], "next", bs, settings, rate(), statuses=dict)
    assert first["backend"] == "claude" and second["backend"] == "codex"
    assert second["tab"]["session_backend"] == "codex"
    assert "resume" not in calls[-1][1]
    assert "User: hello" in calls[-1][2]
    third = tabs.send(tab["id"], "continue", bs, settings,
                      rate("hard"), statuses=dict)
    assert third["tab"]["session_backend"] == "grok"
    assert "--resume" not in calls[-1][1]


def test_busy_tab_refuses_overlap_and_reset():
    tab = tabs.create("fake", "alpha")

    class Busy(Capture):
        def _run(self, prompt):
            with pytest.raises(ValueError, match="already answering"):
                tabs.send(tab["id"], "overlap", bs, cfg(), rate(), statuses=dict)
            with pytest.raises(ValueError, match="wait"):
                tabs.new_session(tab["id"])
            return "Useful answer"

    bs = {"fake": Busy("fake")}
    assert tabs.send(tab["id"], "hello", bs, cfg(), rate(), statuses=dict)["ok"]
    assert tabs.new_session(tab["id"])["history"] == []


def test_close_recreate_during_reply_does_not_attach_old_session(fake_cli, monkeypatch):
    bs = default_backends(free_models={})
    tab = tabs.create("claude", "alpha", backends=bs)
    old_exec = CLIBackend._exec

    def execute(cli, cmd, stdin):
        tabs.close(tab["id"])
        tabs.create("claude", "alpha", backends=bs)
        return old_exec(cli, cmd, stdin)

    monkeypatch.setattr(CLIBackend, "_exec", execute)
    tabs.send(tab["id"], "old answer", bs, cfg(), rate(), statuses=dict)
    saved = tabs.list_tabs()[0]
    assert saved["history"] == [] and not saved["session_id"]


@pytest.mark.parametrize("error", ["No conversation found with session ID abc",
                                  "unknown thread abc", "Session abc does not exist"])
def test_session_missing_messages(error):
    assert session_missing(error)


@pytest.mark.parametrize("name", ["claude", "codex", "grok"])
def test_real_subprocess_with_repository_fake_cli(name, monkeypatch):
    """Exercise stdin, prompt files, JSON and output files through real pipes."""
    import os
    import shutil
    import sys
    from megazword import config

    fake_dir = Path(__file__).resolve().parents[1] / "scripts" / "fake_cli"
    real_which = shutil.which
    monkeypatch.setenv("MZ_SMOKE_PYTHON", sys.executable)
    monkeypatch.setenv("MEGAZWORD_HOME", str(config.HOME))
    monkeypatch.setattr("megazword.backends.shutil.which", lambda exe:
                        str(fake_dir / (exe + (".cmd" if os.name == "nt" else "")))
                        if exe in ("claude", "codex", "grok") else real_which(exe))
    bs = default_backends(free_models={})
    tab = tabs.create(name, "alpha", backends=bs)
    first = tabs.send(tab["id"], "Remember fruit", bs, cfg(), rate(), statuses=dict)
    assert first["ok"]
    session = first["tab"]["session_id"]
    second = tabs.send(tab["id"], 'Fruit? & "special" π', bs, cfg(), rate(), statuses=dict)
    assert second["ok"] and second["tab"]["session_id"] == session
    record = config.HOME / "fake-sessions" / (session + ".json")
    prompts = json.loads(record.read_text())["prompts"]
    assert prompts[1] == 'Fruit? & "special" π'
    record.unlink()  # an expired session in the fake's own persistence store
    recovered = tabs.send(tab["id"], "Recover please", bs, cfg(), rate(), statuses=dict)
    assert recovered["ok"] and recovered["tab"]["session_id"] != session
    assert "started a new session" in recovered["tab"]["session_note"]


@pytest.mark.parametrize("output", ['{bad json', '{}',
                                    '{"session_id":"abc","result":"","is_error":false}',
                                    '{"result":"Useful answer","is_error":false}'])
def test_malformed_claude_answer_does_not_save_a_session(output, fake_cli, monkeypatch):
    monkeypatch.setattr(CLIBackend, "_exec", lambda *args: output)
    bs = default_backends(free_models={})
    tab = tabs.create("claude", "alpha", backends=bs)
    result = tabs.send(tab["id"], "hello", bs, cfg(), rate(), statuses=dict)
    assert not result["ok"]
    assert not tabs.list_tabs()[0]["session_id"] and tabs.list_tabs()[0]["history"] == []


def test_two_tabs_never_resume_each_others_session(fake_cli):
    calls, _ = fake_cli
    bs = default_backends(free_models={})
    a, b = [tabs.create("claude", "alpha", backends=bs) for _ in range(2)]
    a1 = tabs.send(a["id"], "Alice", bs, cfg(), rate(), statuses=dict)
    b1 = tabs.send(b["id"], "Bob", bs, cfg(), rate(), statuses=dict)
    assert a1["tab"]["session_id"] != b1["tab"]["session_id"]
    a2 = tabs.send(a["id"], "continue", bs, cfg(), rate(), statuses=dict)
    assert a2["tab"]["session_id"] == a1["tab"]["session_id"]
    assert calls[-1][1][calls[-1][1].index("--resume") + 1] != b1["tab"]["session_id"]
