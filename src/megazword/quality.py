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


def judge_for(prompt: str, model: str, base: Callable[[str], str | None],
              generate: Callable[..., str] | None = None) -> Callable[[str], str | None]:
    """An escalate() judge: the cheap rule judge first, then the quality check."""
    def judge(text: str) -> str | None:
        return base(text) or check(prompt, text, model, generate)
    return judge
