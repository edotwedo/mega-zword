"""Rates how hard a request is: easy, medium or hard.

Uses a small local model through Ollama. If that isn't available, falls back
to a simple rule so `megazword run` still works.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from . import ollama

RATINGS = ("easy", "medium", "hard")
DEFAULT_RATER_MODEL = "qwen2.5:1.5b"

RATER_PROMPT = """You sort requests for an AI assistant by difficulty.
easy: quick facts, short rewrites, simple one-step questions.
medium: normal coding or writing tasks, explanations, small bug fixes.
hard: multi-step reasoning, designing systems, large or tricky code changes, debugging unknown problems.

Reply with JSON only: {{"rating": "easy" | "medium" | "hard", "reason": "<under 12 words>"}}

Request:
{prompt}"""

HARD_WORDS = ("architect", "design", "refactor", "debug", "prove", "optimi", "migrate",
              "security", "concurren", "whole project", "entire")


@dataclass
class Rating:
    level: str
    reason: str
    source: str  # which rater produced it


def rule_rate(prompt: str) -> Rating:
    text = prompt.lower()
    if any(w in text for w in HARD_WORDS) or len(prompt) > 2000:
        return Rating("hard", "long prompt or hard-task keywords", "rule")
    if len(prompt) < 200 and "\n" not in prompt.strip():
        return Rating("easy", "short single-line prompt", "rule")
    return Rating("medium", "default for mid-size prompts", "rule")


def _from_jev(prompt: str, answers: dict) -> Rating:
    block = answers["difficulty"]
    level = str(block.get("choice", "")).lower().strip()
    probs = block.get("probabilities") or {}
    if level not in RATINGS and probs:
        level = max(probs, key=probs.get)
    if level not in RATINGS:
        raise ValueError(f"unexpected rating {level!r}")
    shown = probs.get(level)
    reason = "jev" if shown is None else f"jev p={shown}"
    # A chosen probability in this band does not settle the level, so raise
    # one step. Hard is already the top. 0.7/0.3 are the skill's thresholds;
    # below 0.5 the choice is the other way, so it is left alone.
    # 0.7 is the edge of confidence, not doubt, so it does not raise.
    if shown is not None and 0.5 <= float(shown) < 0.7 and level != "hard":
        level = "medium" if level == "easy" else "hard"
        reason = f"jev uncertain p={shown}, raised"
    # Small models underrate hard work, so the keyword rule can raise
    # (never lower) the rating. Jev is held to the same floor.
    rule = rule_rate(prompt)
    if rule.level == "hard" and level != "hard":
        return Rating("hard", f"{reason}; raised by rule: {rule.reason}", "jev+rule")
    return Rating(level, reason, "jev")


def rate(prompt: str, model: str = DEFAULT_RATER_MODEL) -> Rating:
    from .decision import JevDecision, pick
    decision = pick()
    if isinstance(decision, JevDecision):
        try:
            from .decision import DIFFICULTY_QUESTION
            answers = decision.choose(prompt[:4000], {"difficulty": DIFFICULTY_QUESTION})
            return _from_jev(prompt, answers)
        except Exception as exc:
            fallback = rule_rate(prompt)
            fallback.reason += f" (jev unavailable: {type(exc).__name__})"
            return fallback
    try:
        raw = ollama.generate(RATER_PROMPT.format(prompt=prompt[:4000]), model,
                              json_format=True, timeout=120)  # first call loads the model
        data = json.loads(raw)
        level = str(data.get("rating", "")).lower().strip()
        if level not in RATINGS:
            raise ValueError(f"unexpected rating {level!r}")
        reason = str(data.get("reason", "")).strip()
        rule = rule_rate(prompt)
        if rule.level == "hard" and level != "hard":
            return Rating("hard", f"{reason}; raised by rule: {rule.reason}", f"local:{model}+rule")
        return Rating(level, reason, f"local:{model}")
    except Exception as exc:
        fallback = rule_rate(prompt)
        fallback.reason += f" (local rater unavailable: {type(exc).__name__})"
        return fallback
