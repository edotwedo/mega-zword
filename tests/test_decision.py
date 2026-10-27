"""Jev decision seam. Fake transport only: no network and no API key."""

import io
import json
import urllib.error

import pytest

from megazword.decision import DODGE_QUESTION, DecisionError, JevDecision, LocalDecision, noul_probability, pick
from megazword.quality import jev_check
from megazword.rater import rate


class _Body:
    def __init__(self, raw: bytes, status: int = 200):
        self._raw = raw
        self.status = status

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _Transport:
    def __init__(self, codes, body=None):
        self.codes = list(codes)
        self.body = body or json.dumps({
            "model": "jev-latest",
            "answers": {"difficulty": {
                "type": "choice", "choice": "medium",
                "probabilities": {"easy": 0.1, "medium": 0.8, "hard": 0.1},
                "confidence": 0.7,
            }},
            "usage": {"input_tokens": 12},
        }).encode()
        self.calls = 0
        self.urls = []
        self.headers = []

    def __call__(self, request, timeout):
        self.calls += 1
        self.urls.append(request.full_url)
        self.headers.append(request.header_items())
        code = self.codes.pop(0)
        if code >= 400:
            raise urllib.error.HTTPError(request.full_url, code, "no", {}, io.BytesIO(b"no"))
        return _Body(self.body)


def test_choice_parse_uses_choice_and_rule_floor(monkeypatch):
    transport = _Transport([200, 200, 200])
    decision = JevDecision("test-key", opener=transport, sleep=lambda _s: None, rng=lambda: 0)
    answers = decision.choose("explain lists", {"difficulty": {"type": "choice"}})
    assert answers["difficulty"]["choice"] == "medium"
    assert answers["difficulty"]["probabilities"]["medium"] == 0.8
    assert transport.urls[0] == "https://api.typesafe.ai/v1/systemone"
    assert ("Authorization", "Bearer test-key") in transport.headers[0]

    monkeypatch.setattr("megazword.decision.pick", lambda: decision)
    assert rate("explain lists").source == "jev"
    raised = rate("design a job queue")
    assert raised.level == "hard" and raised.source == "jev+rule"


def test_docs_noul_shape():
    """The live API puts the probability on "noul". The old reader missed it."""
    answer = {"asks_refund": {"type": "noul", "noul": 0.91}}["asks_refund"]
    assert noul_probability(answer) == 0.91
    assert "probability" not in answer


def test_noul_compat_keys_still_parse():
    assert noul_probability({"type": "noul", "probability": 0.4}) == 0.4
    assert noul_probability({"type": "noul", "probabilities": {"true": 0.2}}) == 0.2


def test_choose_logs_input_tokens():
    transport = _Transport([200])
    decision = JevDecision("k", opener=transport, sleep=lambda _s: None, rng=lambda: 0)
    decision.choose("x", {"difficulty": {"type": "choice"}})
    assert decision.last_usage["input_tokens"] == 12
    assert decision.last_request["model"] == "jev-latest"


def _choice_body(probability, choice="easy"):
    return json.dumps({
        "model": "jev-latest",
        "answers": {"difficulty": {
            "type": "choice", "choice": choice,
            "probabilities": {choice: probability},
            "confidence": probability,
        }},
        "usage": {"input_tokens": 4},
    }).encode()


def test_uncertain_choice_raises_one_level(monkeypatch):
    from megazword.rater import _from_jev
    def answers(probability, choice="easy"):
        return {"difficulty": {"choice": choice, "probabilities": {choice: probability}}}
    raised = _from_jev("explain lists", answers(0.6))
    assert raised.level == "medium" and raised.reason == "jev uncertain p=0.6, raised"
    assert _from_jev("explain lists", answers(0.95)).level == "easy"
    assert _from_jev("explain lists", answers(0.2)).level == "easy"
    assert _from_jev("explain lists", answers(0.6, "medium")).level == "hard"
    assert _from_jev("explain lists", answers(0.70, "medium")).level == "medium"
    assert _from_jev("explain lists", answers(0.69, "medium")).level == "hard"
    assert _from_jev("explain lists", answers(0.50)).level == "medium"
    assert _from_jev("explain lists", answers(0.49)).level == "easy"

    transport = _Transport([200], body=_choice_body(0.6))
    decision = JevDecision("k", opener=transport, sleep=lambda _s: None, rng=lambda: 0)
    monkeypatch.setattr("megazword.decision.pick", lambda: decision)
    assert rate("explain lists").reason == "jev uncertain p=0.6, raised"


def test_mid_noul_is_not_a_dodge():
    class Fake:
        def choose(self, state, questions):
            assert questions["dodge"] is DODGE_QUESTION
            assert questions["dodge"]["criteria"]["false"] == "the answer addresses the request"
            return {"dodge": {"type": "noul", "noul": self.p}}

    fake = Fake()
    for probability in (0.3, 0.5, 0.7):
        fake.p = probability
        assert jev_check("sum 2+2", "4", fake) is None
    fake.p = 0.91
    assert jev_check("sum 2+2", "later", fake) == "quality check: answer does not address the request"


def test_local_decision_refuses_a_noul():
    with pytest.raises(DecisionError, match="cannot answer"):
        LocalDecision().choose("hello", {"dodge": {"type": "noul"}})


def test_429_backs_off_then_succeeds():
    transport = _Transport([429, 429, 200])
    slept = []
    decision = JevDecision("k", opener=transport, sleep=slept.append, rng=lambda: 0)
    answers = decision.choose("x", {"difficulty": {"type": "choice"}})
    assert answers["difficulty"]["choice"] == "medium"
    assert slept == [1.0, 2.0]
    assert transport.calls == 3


def test_401_is_not_retried():
    transport = _Transport([401])
    slept = []
    decision = JevDecision("k", opener=transport, sleep=slept.append, rng=lambda: 0)
    with pytest.raises(DecisionError) as caught:
        decision.choose("x", {"difficulty": {"type": "choice"}})
    assert caught.value.code == 401 and not caught.value.retryable
    assert slept == [] and transport.calls == 1


def test_missing_key_is_local(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert isinstance(pick(), LocalDecision)
