"""Chat: Ctrl+C cancels the running call (not the chat), /cost, history."""

import json
import subprocess
import sys
from dataclasses import dataclass

from megazword import backends as bk
from megazword import chat, config
from megazword.backends import Backend, CLIBackend
from tests.test_cli import FakeBackend, rated


@dataclass
class InterruptOnce(Backend):
    hits: int = 0

    def run(self, prompt):  # Ctrl+C arrives while the AI is working
        self.hits += 1
        if self.hits == 1:
            raise KeyboardInterrupt
        return FakeBackend(self.name, reply="second").run(prompt)


def scripted(*lines):
    it = iter(lines)
    return lambda _prompt: next(it)


def test_ctrl_c_during_call_returns_to_prompt(tmp_path):
    cfg = config.Config(log_path=tmp_path / "log.jsonl")
    cfg.route = {"easy": ["ai"], "medium": [], "hard": []}
    out = []
    code = chat.run({"ai": InterruptOnce("ai")}, cfg, rated("easy"), dict,
                    read=scripted("first", "again", "/quit"), write=out.append)
    text = "\n".join(map(str, out))
    assert code == 0 and "cancelled; back at the prompt" in text
    assert "second: " in text  # the chat kept going and answered the next message


def test_ctrl_c_at_prompt_still_quits(tmp_path):
    def interrupt(_p):
        raise KeyboardInterrupt
    assert chat.run({}, config.Config(log_path=tmp_path / "l"), rated("easy"), dict,
                    read=interrupt, write=lambda _t: None) == 0


def test_ctrl_c_kills_the_cli_process_tree(monkeypatch):
    killed = []
    monkeypatch.setattr(bk, "_kill_tree", lambda proc, reap=True: killed.append(proc.pid))

    def communicate(self, *a, **k):
        raise KeyboardInterrupt
    monkeypatch.setattr(subprocess.Popen, "communicate", communicate)
    b = CLIBackend("x", exe=sys.executable, args=["-c", "pass"])
    try:
        b.run("hi")
        raised = False
    except KeyboardInterrupt:
        raised = True
    assert raised and len(killed) == 1


def test_cost_counts_this_session_only(tmp_path):
    log = tmp_path / "log.jsonl"
    log.write_text(json.dumps({"time": "2020-01-01T00:00:00+00:00", "backend": "old",
                               "est_tokens": 999}) + "\n", encoding="utf-8")
    cfg = config.Config(log_path=log)
    cfg.route = {"easy": ["ai"], "medium": [], "hard": []}
    out = []
    chat.run({"ai": FakeBackend("ai")}, cfg, rated("easy"), dict,
             read=scripted("/cost", "hello", "/cost", "/quit"), write=out.append)
    text = "\n".join(map(str, out))
    assert "No AI calls yet this session." in text
    assert "ai " in text and "1 runs" in text and "old" not in text


def test_history_skipped_without_readline(tmp_path, monkeypatch):
    import builtins
    real = builtins.__import__

    def no_readline(name, *a, **k):
        if name == "readline":
            raise ImportError
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_readline)
    chat._load_history(tmp_path / "chat_history")  # must not raise
