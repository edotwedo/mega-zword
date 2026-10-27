"""Decision seam: Jev when a TypeSafe key is set, otherwise the local rater.

Jev returns calibrated probabilities over fixed options. There is no free-form
text. Without TYPESAFE_API_KEY the seam is LocalDecision and never calls out.
"""

from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.request

DEFAULT_BASE = "https://api.typesafe.ai"
_BACKOFF = (1.0, 2.0, 4.0)


class DecisionError(RuntimeError):
    def __init__(self, message: str, code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class JevDecision:
    """POST /v1/systemone. 401 and 422 are not retried. 429 and 529 back off."""

    def __init__(self, key: str, base_url: str | None = None, opener=None,
                 sleep=time.sleep, rng=random.random):
        base = (base_url or os.environ.get("TYPESAFE_BASE_URL") or DEFAULT_BASE).rstrip("/")
        self.url = base + "/v1/systemone"
        self.key = key
        self.opener = opener or urllib.request.urlopen
        self.sleep = sleep
        self.rng = rng

    def choose(self, state, questions: dict) -> dict:
        body = json.dumps({"model": "jev-latest", "state": state, "questions": questions}).encode()
        attempt = 0
        while True:
            request = urllib.request.Request(
                self.url, data=body, method="POST",
                headers={
                    "Authorization": "Bearer " + self.key,
                    "Content-Type": "application/json",
                    "User-Agent": "megazword-decision/1",
                },
            )
            code, raw = self._post(request)
            if code in (429, 529):
                if attempt >= len(_BACKOFF):
                    raise DecisionError(f"jev HTTP {code}", code, True)
                self.sleep(_BACKOFF[attempt] + self.rng() * 0.25)
                attempt += 1
                continue
            if code in (401, 422) or code >= 400:
                raise DecisionError(f"jev HTTP {code}", code, False)
            payload = json.loads(raw.decode("utf-8"))
            answers = payload.get("answers")
            if not isinstance(answers, dict):
                raise DecisionError("jev response has no answers")
            return answers

    def _post(self, request) -> tuple[int, bytes]:
        try:
            with self.opener(request, timeout=30) as response:
                return getattr(response, "status", 200), response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()


class LocalDecision:
    """Today's rater: qwen2.5:1.5b through Ollama, shaped as a choice answer."""

    def choose(self, state, questions: dict) -> dict:
        from . import ollama
        from .rater import DEFAULT_RATER_MODEL, RATER_PROMPT
        prompt = state if isinstance(state, str) else json.dumps(state)
        raw = ollama.generate(RATER_PROMPT.format(prompt=prompt[:4000]),
                              DEFAULT_RATER_MODEL, json_format=True, timeout=120)
        data = json.loads(raw)
        level = str(data.get("rating", "")).lower().strip()
        return {"difficulty": {"type": "choice", "choice": level,
                               "probabilities": {level: 1.0}}}


def pick():
    """JevDecision when TYPESAFE_API_KEY is set, else LocalDecision."""
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key:
        return LocalDecision()
    return JevDecision(key)


def noul_probability(answer: dict) -> float | None:
    """Boolean probability from a noul answer. These answers have no confidence."""
    if not isinstance(answer, dict):
        return None
    if "probability" in answer:
        return float(answer["probability"])
    probs = answer.get("probabilities")
    if isinstance(probs, dict) and "true" in probs:
        return float(probs["true"])
    return None
