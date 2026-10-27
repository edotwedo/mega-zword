"""Optional answer-quality check: does the answer actually address the request?

The refusal/empty rules in escalate.py catch obvious non-answers. This adds a
cheap second opinion from the local rater model for answers that dodge,
answer a different question, or only promise to do the work. Off by default
(`quality_check = true` in config.toml turns it on), because a small local
model can be wrong and every false alarm costs a stronger AI's usage.

It only ever flags; it never blocks an answer on its own errors. If Ollama is
down or replies with junk, the answer is kept.
"""

from __future__ import annotations

import json
from typing import Callable

from . import ollama

QUALITY_PROMPT = """You check whether an AI's answer actually addresses a request.
Say "dodge" only if the answer clearly fails: it talks about something else,
only says it will do the work later, asks for information the request already
gave, or gives no real content. Short correct answers are fine. When unsure, say "ok".

Reply with JSON only: {{"verdict": "ok" | "dodge", "reason": "<under 12 words>"}}

Request:
{prompt}

Answer:
{answer}"""

# Long requests and answers are trimmed; the check only needs the gist.
PROMPT_CHARS = 1500
ANSWER_CHARS = 2500


def check(prompt: str, answer: str, model: str,
          generate: Callable[..., str] | None = None) -> str | None:
    """A reason if the answer looks like a dodge, else None."""
    generate = generate or ollama.generate
    try:
        raw = generate(QUALITY_PROMPT.format(prompt=prompt[:PROMPT_CHARS],
                                             answer=answer[:ANSWER_CHARS]),
                       model, json_format=True, timeout=60)
        data = json.loads(raw)
    except Exception:
        return None
    if str(data.get("verdict", "")).lower().strip() != "dodge":
        return None
    reason = str(data.get("reason", "")).strip() or "doesn't address the request"
    return f"quality check: {reason}"


def jev_check(prompt: str, answer: str, decision) -> str | None:
    """A dodge reason from a noul question. Errors, and an unsettled call, keep the answer.

    Above 0.7 is a dodge. Below 0.3 is not. The band between is not settled,
    so it is not treated as yes.
    """
    from .decision import DODGE_QUESTION, noul_probability
    try:
        answers = decision.choose(
            {"request": prompt[:PROMPT_CHARS], "answer": answer[:ANSWER_CHARS]},
            {"dodge": DODGE_QUESTION},
        )
        probability = noul_probability(answers.get("dodge"))
    except Exception:
        return None
    if probability is None or probability <= 0.7:
        return None
    return "quality check: answer does not address the request"


def judge_for(prompt: str, model: str, base: Callable[[str], str | None],
              generate: Callable[..., str] | None = None) -> Callable[[str], str | None]:
    """An escalate() judge: the cheap rule judge first, then Jev or the local check.

    A caller-supplied generate (tests, and the no-key path) keeps today's Ollama
    check. Jev is used only when a key is set and nobody injected a generator.
    """
    def judge(text: str) -> str | None:
        ruled = base(text)
        if ruled:
            return ruled
        if generate is None:
            from .decision import JevDecision, pick
            decision = pick()
            if isinstance(decision, JevDecision):
                return jev_check(prompt, text, decision)
        return check(prompt, text, model, generate)
    return judge
