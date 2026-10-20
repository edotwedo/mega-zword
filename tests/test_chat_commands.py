"""Chat slash commands and B12 levels in chat (fake backends only)."""

from dataclasses import dataclass, field

from megazword import config
from megazword.backends import CLIBackend
from megazword.rater import Rating

from test_chat import FakeBackend, session


@dataclass
class FakeClaude(CLIBackend):
    """Looks like the real claude CLI to apply_levels, but never runs anything."""
    seen: list[list[str]] = field(default_factory=list)

    def available(self) -> bool:
        return True

    def _run(self, prompt: str) -> str:
        self.seen.append(list(self.args))
        return "ok"


def _levels_cfg():
    cfg = config.Config(route={"easy": ["claude"], "medium": ["claude"], "hard": ["claude"]})
    cfg.levels = {"claude": {"hard": ("opus-x", "high"), "medium": ("sonnet-x", "")}}
    return cfg


def test_chat_applies_the_rated_level_model_without_sticking():
    claude = FakeClaude("claude", exe="claude", args=["-p"])
    ratings = iter([Rating("hard", "test", "fake"), Rating("easy", "test", "fake")])
    _, output, _, backends = session(["big job", "small job", "/quit"],
                                     {"claude": claude}, _levels_cfg(),
                                     lambda p: next(ratings))
    # Each turn runs on its own copy; the shared table keeps the plain CLI.
    assert backends["claude"].args == ["-p"]
    assert any("using claude (opus-x high)" in line for line in output)
    assert any(line.endswith("using claude") for line in output)


def test_pinned_chat_uses_the_medium_level():
    claude = FakeClaude("claude", exe="claude", args=["-p"])
    _, output, _, _ = session(["/model claude", "hi", "/quit"], {"claude": claude},
                              _levels_cfg())
    assert "[megazword] using claude (sonnet-x) (pinned)" in output


def test_help_and_model_listing():
    _, output, _, _ = session(["/help", "/model", "/model nope", "/quit"])
    assert any(line.startswith("/help /quit") for line in output)
    assert "Models: fake" in output
    assert "Unknown AI 'nope'. Choose from: fake" in output


def test_note_decide_and_history():
    _, output, _, _ = session(["/history", "/note", "/note buy milk", "/decide ship it",
                               "/history", "/quit"])
    assert "No project memory yet." in output
    assert "Usage: /note <text>" in output
    assert output.count("[megazword] saved to chat-test memory") == 2
    history = [line for line in output if "buy milk" in line or "ship it" in line]
    assert len(history) == 2
    assert any("decision" in line and "ship it" in line for line in history)


def test_context_toggle_adds_memory_to_the_prompt():
    calls = []

    @dataclass
    class Plain(FakeBackend):  # a fixed answer, so memory can't come back via history
        def _run(self, prompt: str) -> str:
            calls.append(prompt)
            return "ok"

    backends = {"fake": Plain("fake")}
    _, output, _, _ = session(["/context maybe", "/note remember the oven",
                               "/context on", "first", "/context off", "second", "/quit"],
                              backends)
    assert "Usage: /context on|off" in output
    assert "Project memory context on." in output
    assert "remember the oven" in calls[0]
    assert "remember the oven" not in calls[1]


def test_cost_counts_this_sessions_runs():
    _, output, _, _ = session(["/cost", "hello", "/cost", "/quit"])
    assert "No AI calls yet this session." in output
    assert any(line.startswith("fake") and "1 runs" in line for line in output)


def test_no_installed_ai_keeps_chatting():
    cfg = config.Config(route={"easy": [], "medium": [], "hard": []})
    result, output, _, _ = session(["hello", "/quit"], cfg=cfg)
    assert result == 0
    assert "[megazword] no installed AI for a easy task" in output


def test_ctrl_c_during_a_call_returns_to_the_prompt():
    @dataclass
    class Interrupting(FakeBackend):
        def _run(self, prompt: str) -> str:
            raise KeyboardInterrupt

    result, output, _, _ = session(["hello", "/quit"], {"fake": Interrupting("fake")})
    assert result == 0
    assert any("cancelled; back at the prompt" in line for line in output)
