"""Jev decision seam. Fake transport only: no network and no API key."""

import io
import json
import urllib.error

import pytest

from megazword.decision import DecisionError, JevDecision, LocalDecision, noul_probability, pick
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
            "usage": {},
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


def test_noul_parse_has_no_confidence():
    assert noul_probability({"type": "noul", "probability": 0.91}) == 0.91
    assert noul_probability({"type": "noul", "probabilities": {"true": 0.2}}) == 0.2
    assert "confidence" not in {"type": "noul", "probability": 0.91}


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
