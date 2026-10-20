"""Escalation and the Ollama backend. Fakes only: no real AIs, no network."""

from dataclasses import dataclass, field

import pytest

from megazword import ollama
from megazword.backends import Backend, OllamaBackend, default_backends
from megazword.escalate import (
    Attempt,
    build_retry_prompt,
    escalate,
    looks_failed,
)


@dataclass
class Fake(Backend):
    """Records each prompt. Raises RuntimeError('boom') when `fail` is set."""

    reply: str = "done"
    fail: bool = False
    prompts: list[str] = field(default_factory=list)

    def _run(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.fail:
            raise RuntimeError("boom")
        return self.reply


# --- looks_failed -----------------------------------------------------------

@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_empty_answer_is_a_failure(text):
    assert looks_failed(text) == "empty answer"


@pytest.mark.parametrize("text", [
    "I can't help with that.",
    "I cannot assist with this request.",
    "I'm unable to help.",
    "I am not able to assist with your request.",
    "Sorry, but I can't help with that.",
    "I'm sorry, I am unable to help.",
    "Unfortunately, I must decline this request.",
    "As an AI, I must refuse.",
    "As an AI language model, I cannot help with that.",
    "I can't.",
    "I cannot.",
    "I'm unable.",
    "I won’t help with that.",  # curly apostrophe
    "I can't help with that. Sorry.",
    "No, I can't assist with this.",
    "I must decline.",
    "I cannot provide that.",
    "I can't do this.",
    "I won't help.",
])
def test_refusals_are_failures(text):
    assert looks_failed(text) == "looks like a refusal"


@pytest.mark.parametrize("text", [
    "You can't use a set here because the tests depend on order. Use a list.",
    "The parser can't return None. Raise ValueError and add a test for empty input.",
    "I can't find a bug here. The tests pass.",
    "I'm unable to reproduce the crash. It passes on Python 3.11.",
    "I can't do this without the error log.",
    "I can't provide enough detail yet, the log is truncated.",
    "I must decline to use a global here and pass the config in instead.",
    "def add(a, b):\n    return a + b\n",
    "No, use a list.",
    "Sorry, the tests can't run yet. Start the database and retry.",
    "I can't help with that. " + ("Use a list and keep the original order. " * 3),
])
def test_normal_answers_that_say_cant_are_kept(text):
    assert looks_failed(text) is None


def test_looks_failed_keeps_a_sentence_that_says_success():
    assert looks_failed("The deploy was a success after the tests passed.") is None
    assert looks_failed("SUCCESS") is None


def test_long_answer_is_not_judged():
    essay = "Here is a full explanation. " + ("You can't skip the check. " * 30)
    assert len(essay) > 320
    assert looks_failed(essay) is None


# --- build_retry_prompt -----------------------------------------------------

def test_retry_prompt_without_rejections_is_the_original():
    assert build_retry_prompt("same", []) == "same"
    assert build_retry_prompt("same", [Attempt("a", True, None, "hi")]) == "same"


def test_retry_prompt_includes_who_why_and_a_trimmed_answer():
    answer = ("Q" * 2000) + "TAIL"
    text = build_retry_prompt("fix the bug", [
        Attempt("grok", True, "looks like a refusal", answer),
        Attempt("codex", False, "failed: boom", ""),
    ])
    assert text.startswith("fix the bug\n")
    assert "- grok: looks like a refusal" in text
    assert "- codex: failed: boom" in text
    assert "TAIL" not in text
    assert text.count("Q") == 1497
    assert "..." in text
    # A crash has no answer, so it doesn't get an answer block of its own.
    assert text.count("  Answer:") == 1


def test_retry_prompt_keeps_multiline_answer():
    text = build_retry_prompt("task", [
        Attempt("grok", True, "looks like a refusal", "line one\nline two"),
    ])
    assert "  line one" in text
    assert "  line two" in text


# --- escalate ---------------------------------------------------------------

def test_first_good_answer_stops_and_does_not_escalate():
    first = Fake("cheap", reply="the list keeps order")
    later = Fake("strong", reply="unused")
    seen = []
    out = escalate("task", [first, later],
                   on_attempt=lambda name, result, reason: seen.append((name, result, reason)))
    assert out.result is seen[0][1]
    assert out.result.text == "the list keeps order"
    assert out.result.backend == "cheap"
    assert out.escalated is False
    assert [(name, reason) for name, _, reason in seen] == [("cheap", None)]
    assert first.prompts == ["task"]
    assert later.prompts == []
    assert out.attempts[-1].reason is None
    assert out.attempts[-1].ok is True


def test_backend_failure_moves_up_and_passes_the_error():
    cheap = Fake("cheap", fail=True)
    strong = Fake("strong", reply="fixed")
    notes = []
    out = escalate("task", [cheap, strong],
                   on_attempt=lambda name, result, reason: notes.append((name, result.ok, reason)))
    assert notes == [("cheap", False, "failed: boom"), ("strong", True, None)]
    assert out.escalated is True
    assert out.result.backend == "strong"
    assert out.result.text == "fixed"
    assert cheap.prompts == ["task"]
    assert strong.prompts == [build_retry_prompt("task", out.attempts[:1])]
    assert "Answer:" not in strong.prompts[0]
    assert out.attempts[0].ok is False


def test_refusal_moves_up_and_passes_the_answer():
    cheap = Fake("cheap", reply="I can't help with that.")
    strong = Fake("strong", reply="sort the list and add a test")
    out = escalate("do the thing", [cheap, strong])
    assert out.escalated is True
    assert out.result.text == "sort the list and add a test"
    assert cheap.prompts == ["do the thing"]
    assert "I can't help with that." in strong.prompts[0]
    assert "looks like a refusal" in strong.prompts[0]
    assert out.attempts[0].ok is True
    assert out.attempts[0].reason == "looks like a refusal"
    assert strong.prompts == [build_retry_prompt("do the thing", out.attempts[:1])]


def test_empty_reply_is_rejected_by_the_default_judge():
    blank = Fake("cheap", reply="   ")
    strong = Fake("strong", reply="real")
    out = escalate("task", [blank, strong])
    assert out.attempts[0].reason == "empty answer"
    assert out.result.backend == "strong"
    assert "empty answer" in strong.prompts[0]


def test_chain_of_failure_then_refusal_then_success():
    cheap = Fake("cheap", fail=True)
    mid = Fake("mid", reply="I'm unable to help.")
    strong = Fake("strong", reply="done")
    out = escalate("task", [cheap, mid, strong])
    assert [a.name for a in out.attempts] == ["cheap", "mid", "strong"]
    assert out.escalated is True
    assert out.result.backend == "strong"
    assert strong.prompts == [build_retry_prompt("task", out.attempts[:2])]
    assert "failed: boom" in strong.prompts[0]
    assert "I'm unable to help." in strong.prompts[0]
    assert cheap.prompts == ["task"]
    # The middle model already sees the first failure.
    assert "failed: boom" in mid.prompts[0]


def test_all_rejected_returns_no_result_and_did_escalate():
    out = escalate("task", [Fake("a", fail=True), Fake("b", reply="I can't help.")])
    assert out.result is None
    assert out.escalated is True
    assert [a.name for a in out.attempts] == ["a", "b"]
    assert all(a.reason for a in out.attempts)


def test_only_backend_failing_does_not_count_as_escalated():
    out = escalate("task", [Fake("a", fail=True)])
    assert out.result is None
    assert out.escalated is False
    assert len(out.attempts) == 1


def test_no_backends():
    out = escalate("task", [])
    assert out.result is None
    assert out.attempts == []
    assert out.escalated is False


def test_judge_is_not_called_when_the_backend_crashes():
    seen = []

    def judge(text):
        seen.append(text)
        return None

    out = escalate("task", [Fake("cheap", fail=True), Fake("strong", reply="ok")],
                   judge=judge)
    assert seen == ["ok"]
    assert out.result.backend == "strong"
    assert out.attempts[0].reason == "failed: boom"


def test_custom_judge_and_disabled_judge():
    short = Fake("a", reply="no")
    long = Fake("b", reply="yyyy")
    out = escalate("task", [short, long],
                   judge=lambda text: "too short" if len(text) < 4 else None)
    assert out.result.backend == "b"
    assert out.attempts[0].reason == "too short"
    assert "too short" in long.prompts[0]

    refusal = Fake("a", reply="I can't help with that.")
    kept = escalate("task", [refusal], judge=None)
    assert kept.result.backend == "a"
    assert kept.escalated is False
    assert kept.attempts[0].reason is None


def test_start_after_skips_that_backend_and_cheaper_ones():
    cheap = Fake("cheap", reply="c")
    mid = Fake("mid", reply="m")
    strong = Fake("strong", reply="s")
    called = []
    out = escalate(
        "task", [cheap, mid, strong],
        start_after="mid", prior_answer="the mid answer was vague",
        on_attempt=lambda name, result, reason: called.append(name),
    )
    assert cheap.prompts == [] and mid.prompts == []
    assert called == ["strong"]
    assert out.escalated is True
    assert out.result.text == "s"
    assert out.attempts[0].name == "mid"
    assert out.attempts[0].reason == "not good enough"
    assert out.attempts[0].answer == "the mid answer was vague"
    assert out.attempts[0].ok is True
    assert out.attempts[1].name == "strong"
    assert out.attempts[1].reason is None
    assert "the mid answer was vague" in strong.prompts[0]
    assert "not good enough" in strong.prompts[0]
    assert strong.prompts == [build_retry_prompt("task", out.attempts[:1])]


def test_start_after_with_nothing_stronger_left():
    only = Fake("only", reply="x")
    out = escalate("task", [only], start_after="only", prior_answer="old")
    assert only.prompts == []
    assert out.result is None
    assert out.escalated is False
    assert out.attempts[0].name == "only"
    assert out.attempts[0].reason == "not good enough"


def test_unknown_start_after_still_passes_the_old_answer():
    cheap = Fake("cheap", reply="yes")
    out = escalate("task", [cheap], start_after="ghost", prior_answer="old answer")
    assert out.result.backend == "cheap"
    assert out.escalated is True
    assert "old answer" in cheap.prompts[0]
    assert out.attempts[0].name == "ghost"
    assert "- ghost: not good enough" in cheap.prompts[0]


def test_prior_answer_without_start_after_is_context_for_the_first():
    cheap = Fake("cheap", reply="yes")
    out = escalate("task", [cheap], prior_answer="previous try")
    assert out.escalated is True
    assert "previous try" in cheap.prompts[0]
    assert out.attempts[0].name == "previous"


def test_later_backends_are_not_called_after_success():
    third = Fake("third", reply="nope")
    out = escalate("task", [Fake("a", reply="yes"), Fake("b", reply="no"), third])
    assert third.prompts == []
    assert out.escalated is False
    assert [a.name for a in out.attempts] == ["a"]


# --- OllamaBackend ----------------------------------------------------------

def test_ollama_backend_calls_the_local_client(monkeypatch):
    seen = {}

    def fake_generate(prompt, model, url, timeout=60, **kwargs):
        seen["generate"] = (prompt, model, url, timeout, kwargs)
        return "  hello  "

    def fake_reachable(url, timeout=2):
        seen["probe"] = (url, timeout)
        return True

    monkeypatch.setattr(ollama, "generate", fake_generate)
    monkeypatch.setattr(ollama, "reachable", fake_reachable)
    backend = OllamaBackend("local", model="qwen2.5:1.5b",
                            url="http://127.0.0.1:9", timeout=12)
    assert backend.available() is True
    result = backend.run("ping")
    assert seen["probe"] == ("http://127.0.0.1:9", 2)
    assert seen["generate"] == ("ping", "qwen2.5:1.5b", "http://127.0.0.1:9", 12, {})
    assert result.ok is True
    assert result.text == "hello"
    assert result.backend == "local"
    assert result.error == ""


def test_ollama_backend_unavailable_when_server_is_down(monkeypatch):
    monkeypatch.setattr(ollama, "reachable", lambda url, timeout=2: False)
    backend = OllamaBackend("local", model="m", url="http://down")
    assert backend.available() is False


def test_ollama_backend_defaults_the_url():
    backend = OllamaBackend("local", model="m")
    assert backend.url == ollama.DEFAULT_URL
    assert backend.model == "m"


def test_ollama_backend_reports_client_errors(monkeypatch):
    def down(*args, **kwargs):
        raise OSError("refused")

    monkeypatch.setattr(ollama, "generate", down)
    result = OllamaBackend("local", model="m", url="http://127.0.0.1:9").run("ping")
    assert result.ok is False
    assert "refused" in result.error
    assert result.text == ""


def test_ollama_is_available_as_a_zero_cost_default_backend():
    assert isinstance(default_backends()["ollama"], OllamaBackend)
