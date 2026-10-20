"""Move up to a stronger AI when a cheaper one fails or refuses.

The list is cheapest first. The first good answer wins. Each later AI sees
the original prompt plus who tried already, why that attempt was rejected,
and the answer (trimmed), so it can do better.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .backends import Backend, Result

# A rejected answer pasted into the next prompt. Long enough to be useful,
# short enough that the next model still sees the original request.
ANSWER_CHARS = 1500

# Past this length the reply is doing real work. Refusal checks stay on
# short non-answers so a normal sentence that merely says "can't" is kept.
_MAX_CHECKED = 320

# Whole answer is nothing but "I can't" / "I'm unable" (optional period).
_BARE = frozenset({
    "i can't",
    "i cannot",
    "i'm unable",
    "i am unable",
    "i'm not able",
    "i am not able",
})

# Opening of a decline, matched only at the start (after an optional apology).
# looks_failed keeps the longest phrase that matches.
_PHRASES = (
    "i'm not able to assist",
    "i am not able to assist",
    "i'm not able to help",
    "i am not able to help",
    "i'm not allowed to help",
    "i am not allowed to help",
    "i'm unable to assist",
    "i am unable to assist",
    "i'm unable to comply",
    "i am unable to comply",
    "i'm unable to help",
    "i am unable to help",
    "i cannot fulfill",
    "i can't fulfill",
    "i cannot assist",
    "i can't assist",
    "i cannot comply",
    "i can't comply",
    "i cannot answer",
    "i can't answer",
    "i cannot provide",
    "i can't provide",
    "i cannot support",
    "i can't support",
    "i will not help",
    "i won't help",
    "i cannot help",
    "i can't help",
    "i cannot do that",
    "i can't do that",
    "i cannot do this",
    "i can't do this",
    "i must decline",
    "i must refuse",
    "against my guidelines",
)

# What may follow a decline phrase and still be only a refusal.
# "I can't do this without the log" does not match, so it is kept.
_TAILS = frozenset({
    "",
    "that",
    "this",
    "it",
    "you",
    "this request",
    "that request",
    "your request",
    "this task",
    "that task",
    "your task",
    "this question",
    "that question",
    "your question",
    "assistance",
    "with that",
    "with this",
    "with it",
    "with this request",
    "with that request",
    "with your request",
    "with this task",
    "with that task",
    "with your task",
    "with your question",
    "with this question",
    "you with that",
    "you with this",
    "you with this request",
    "you with that request",
    "you with your request",
    "this request for you",
})

# Peeled only from the front, longest first.
_LEADS = (
    "as an ai language model",
    "as a language model",
    "as an ai",
    "i'm sorry",
    "i am sorry",
    "unfortunately",
    "apologies",
    "i apologize",
    "sorry",
    "no",
)

# Shown on the attempt Phil already turned down, and passed to the next AI.
USER_REJECTED = "not good enough"


@dataclass
class Attempt:
    """One try. `reason` is why it was rejected; None if this answer was kept."""

    name: str
    ok: bool
    reason: str | None = None
    answer: str = ""


@dataclass
class EscalationResult:
    """`result` is the first good answer, or None if every backend was rejected."""

    result: Result | None
    attempts: list[Attempt]
    escalated: bool


def looks_failed(text: str) -> str | None:
    """A reason if `text` is empty or is basically a refusal, else None.

    Conservative: the decline has to open a short reply and leave almost
    nothing else. "You can't use a set here" is a normal answer.
    """
    raw = (text or "").strip()
    if not raw:
        return "empty answer"
    flat = " ".join(raw.replace("\u2019", "'").split())
    if len(flat) > _MAX_CHECKED:
        return None
    peeled = _peel_lead(flat.lower())
    if peeled.strip(" .!") in _BARE:
        return "looks like a refusal"
    matched = [phrase for phrase in _PHRASES if peeled.startswith(phrase)]
    if not matched:
        return None
    # Longest phrase wins, so "i can't help" is not judged as a shorter opener.
    phrase = max(matched, key=len)
    if _only_a_refusal(peeled, phrase):
        return "looks like a refusal"
    return None


def build_retry_prompt(prompt: str, attempts: list[Attempt]) -> str:
    """Original prompt plus a short note on each rejected attempt."""
    rejected = [a for a in attempts if a.reason]
    if not rejected:
        return prompt
    lines = ["Earlier attempts were rejected. Do better."]
    for attempt in rejected:
        lines.append(f"- {attempt.name}: {attempt.reason}")
        answer = _trim(attempt.answer)
        if answer:
            lines.append("  Answer:")
            lines.extend(f"  {line}" for line in answer.splitlines())
    lines.append("")
    lines.append("Answer the original request. Don't repeat the same failure.")
    return prompt.rstrip("\r\n") + "\n\n" + "\n".join(lines)


def escalate(prompt: str, backends: list[Backend],
             judge: Callable[[str], str | None] | None = looks_failed,
             on_attempt: Callable[[str, Result, str | None], None] | None = None,
             start_after: str | None = None,
             prior_answer: str | None = None) -> EscalationResult:
    """Run `backends` cheapest first. Stop at the first answer `judge` accepts.

    `start_after` skips that backend and anything before it (Phil already
    rejected that answer). `prior_answer` is included in the context block.
    `judge` None means "only a crashed backend counts as failure".
    `on_attempt(name, result, reason)` runs after each backend that actually
    ran; `reason` is None when the answer was kept.

    `escalated` is true when a backend ran after an earlier attempt was
    rejected. It is false when the first backend we were willing to run
    answered well, or when nothing ran.
    """
    attempts: list[Attempt] = []
    if start_after is not None or prior_answer:
        attempts.append(Attempt(
            start_after or "previous",
            True,
            USER_REJECTED,
            prior_answer or "",
        ))

    names = [b.name for b in backends]
    skipping = start_after is not None and start_after in names
    prior_rejection = bool(attempts)
    escalated = False

    for backend in backends:
        if skipping:
            if backend.name == start_after:
                skipping = False
            continue

        if prior_rejection:
            escalated = True
        outgoing = build_retry_prompt(prompt, attempts) if prior_rejection else prompt
        result = backend.run(outgoing)

        if not result.ok:
            reason = f"failed: {result.error}" if result.error else "failed"
        elif judge is not None:
            reason = judge(result.text) or None
        else:
            reason = None

        attempts.append(Attempt(backend.name, result.ok, reason, result.text))
        if on_attempt is not None:
            on_attempt(backend.name, result, reason)
        if reason:
            prior_rejection = True
            continue
        return EscalationResult(result, attempts, escalated)

    return EscalationResult(None, attempts, escalated)


def _peel_lead(text: str) -> str:
    """Drop a leading apology or "as an AI" so the decline sits at column 0."""
    for _ in range(3):
        for lead in _LEADS:
            if text.startswith(lead):
                text = text[len(lead):].lstrip(" ,.:;-")
                if text.startswith("but "):
                    text = text[4:]
                break
        else:
            break
    return text


def _first_sentence(text: str) -> tuple[str, str]:
    for i, ch in enumerate(text):
        if ch in ".!?":
            return text[:i], text[i + 1:].strip()
    return text, ""


def _only_a_refusal(peeled: str, phrase: str) -> bool:
    first, after = _first_sentence(peeled)
    tail = first[len(phrase):].strip(" .,!?;:\"'")
    if tail not in _TAILS:
        return False
    return len(after) <= 48


def _trim(text: str, limit: int = ANSWER_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."
