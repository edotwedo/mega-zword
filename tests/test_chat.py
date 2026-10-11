from dataclasses import dataclass

import pytest

from megazword import config
from megazword.backends import Backend
from megazword.chat import run
from megazword.rater import Rating


@dataclass
class FakeBackend(Backend):
    calls: list[str] | None = None

    def _run(self, prompt: str) -> str:
        if self.calls is not None:
            self.calls.append(prompt)
        return f"answer to {prompt[-80:]}"


def session(lines, backends=None, cfg=None, rater=None):
    remaining = iter(lines)
    prompts = []
    output = []

    def read(prompt):
        prompts.append(prompt)
        item = next(remaining)
        if isinstance(item, BaseException):
            raise item
        return item

    backends = backends or {"fake": FakeBackend("fake", calls=[])}
    cfg = cfg or config.Config(route={"easy": ["fake"], "medium": ["fake"],
                                      "hard": ["fake"]})
    cfg.log_path = config.HOME / "log.jsonl"
    result = run(backends, cfg, rater or (lambda p: Rating("easy", "test", "fake")),
                 statuses=dict, read=read, write=output.append, project="chat-test")
    return result, output, prompts, backends


def test_answer_and_second_message_gets_conversation_context():
    result, output, _, backends = session(["hello", "what next?", "/quit"])
    assert result == 0
    assert len(backends["fake"].calls) == 2
    assert "[New message]\n\nhello" in backends["fake"].calls[0]
    assert "[Conversation so far]" in backends["fake"].calls[1]
    assert "User: hello" in backends["fake"].calls[1]
    assert any(line.startswith("answer to") for line in output)


def test_model_pin_then_auto():
    calls_a, calls_b = [], []
    backends = {"a": FakeBackend("a", calls=calls_a), "b": FakeBackend("b", calls=calls_b)}
    cfg = config.Config(route={"easy": ["a"], "medium": ["a"], "hard": ["a"]})
    selected = []
    def rate(prompt):
        selected.append(prompt)
        return Rating("easy", "test", "fake")
    session(["/model b", "pinned", "/auto", "automatic", "/quit"], backends, cfg, rate)
    assert len(calls_b) == 1 and len(calls_a) == 1
    assert len(selected) == 1


def test_retry_uses_retry_last_and_captures_answer():
    calls_a, calls_b = [], []
    backends = {"a": FakeBackend("a", calls=calls_a), "b": FakeBackend("b", calls=calls_b)}
    cfg = config.Config(route={"easy": ["a"], "medium": ["a"], "hard": ["b"]})
    result, output, _, _ = session(["first", "/retry", "/quit"], backends, cfg)
    assert result == 0
    assert len(calls_a) == len(calls_b) == 1
    assert any("answer to" in line for line in output)


def test_clear_forgets_conversation():
    _, _, _, backends = session(["first", "/clear", "second", "/quit"])
    assert "[Conversation so far]" not in backends["fake"].calls[1]


@pytest.mark.parametrize("lines,expected", [
    (["first\\", "second", "/quit"], "first\nsecond"),
    (["<<<", "first", "second", ">>>", "/quit"], "first\nsecond"),
])
def test_multiline_input(lines, expected):
    _, _, _, backends = session(lines)
    assert expected in backends["fake"].calls[0]


def test_quit_and_eof_exit_cleanly():
    assert session(["/quit"])[0] == 0
    assert session([EOFError()])[0] == 0
    assert session([KeyboardInterrupt()])[0] == 0


def test_unknown_slash_command_is_helpful():
    _, output, _, _ = session(["/wat", "/quit"])
    assert any("Unknown command '/wat'" in line and "/help" in line for line in output)

