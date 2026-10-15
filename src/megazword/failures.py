"""Explain a failed AI call in plain English, with the fix.

Kinds: usage limit (see limits.py), not logged in, model access, network down,
CLI missing, timeout. Anything else is left as the raw error. Only usage limits
ever mark an AI out: an auth or network problem is fixed by you, not by
waiting, so the AI stays in the rotation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .limits import detect as detect_limit

# Exact commands from each CLI's --help (checked 2026-10-11).
LOGIN_FIX = {
    "kimi": "set OPENROUTER_API_KEY (see `megazword doctor`)",
    "deepseek": "set OPENROUTER_API_KEY (see `megazword doctor`)",
    "qwen-coder": "set OPENROUTER_API_KEY (see `megazword doctor`)",
    "claude": "run `claude auth login`",
    "codex": "run `codex login`",
    "grok": "run `grok login`",
    "gemini": "run `agy` once and sign in",
    "openrouter": "set OPENROUTER_API_KEY (see `megazword doctor`)",
    "groq": "set GROQ_API_KEY (see `megazword doctor`)",
    "cloudflare": "set CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID (see `megazword doctor`)",
    "zai": "set ZAI_API_KEY (see `megazword doctor`)",
    "gemini-api": "set GOOGLE_AI_API_KEY (see `megazword doctor`)",
    "nvidia": "set NVIDIA_API_KEY (see `megazword doctor`)",
    "mistral": "set MISTRAL_API_KEY (see `megazword doctor`)",
}

_AUTH = re.compile(
    r"not logged in|not signed in|please (?:log|sign) ?in|log ?in required|login required"
    r"|unauthori[sz]ed|\b401\b|\bforbidden\b|authentication (?:failed|required|error)|invalid api key"
    r"|invalid x-api-key|(?:token|session|credentials?) (?:has )?expired|expired (?:token|session)"
    r"|no api key|missing api key|run .{0,20}\blogin\b", re.I)
_MODEL_ACCESS = re.compile(
    r"only available on (?:agentic )?harnesses|model (?:is restricted|not available|access denied)"
    r"|not available to this app|app-restricted|model gate", re.I)
_NETWORK = re.compile(
    r"getaddrinfo|enotfound|eai_again|name or service not known|could not resolve host"
    r"|temporary failure in name resolution|nodename nor servname|network is unreachable"
    r"|no route to host|econnrefused|econnreset|connection (?:refused|reset|aborted)"
    r"|failed to establish a new connection|unable to connect|no internet|you appear to be offline"
    r"|urlopen error|socket\.gaierror|winerror 1100[14]", re.I)
_MISSING = re.compile(r"is not installed or not on PATH|No such file or directory: '[^']*(claude|codex|grok|gemini|agy)", re.I)
_TIMEOUT = re.compile(r"gave no answer within (\d+)s", re.I)


@dataclass
class Failure:
    kind: str     # limit | auth | network | missing | timeout
    reason: str   # one plain-English line
    fix: str


def classify(ai: str, error: str) -> Failure | None:
    """Plain-English reason and fix for `error`, or None if it's unfamiliar."""
    text = (error or "").replace("’", "'")
    if detect_limit(text):
        return Failure("limit", f"{ai} is out of usage for now",
                       f"wait for the reset, or `megazword out {ai} --clear` if it's wrong")
    if _MODEL_ACCESS.search(text):
        return Failure("access", f"{ai}'s selected model is restricted for this app",
                       "choose a model whose provider allows this app to use its API")
    if _AUTH.search(text):
        return Failure("auth", f"{ai} isn't logged in (or its login expired)",
                       LOGIN_FIX.get(ai, f"sign in to {ai} again"))
    if _NETWORK.search(text):
        return Failure("network", f"{ai} couldn't reach the internet",
                       "check your Wi-Fi/connection, then try again")
    if _MISSING.search(text):
        return Failure("missing", f"{ai} isn't installed on this computer",
                       "install it, or run `megazword doctor` to see what's available")
    if m := _TIMEOUT.search(text):
        return Failure("timeout", f"{ai} gave no answer within {m.group(1)}s and was stopped",
                       f"try again, or raise its limit: [timeouts] {ai} = 900 in config.toml")
    return None


def line(f: Failure) -> str:
    return f"{f.reason}. Fix: {f.fix}."


class NetworkDown(Exception):
    """Raised to stop an escalation chain once the connection looks dead."""


class Watch:
    """Tracks consecutive network failures across one chain of attempts.
    Two in a row means it's the connection, not the AI: stop trying others."""

    def __init__(self, limit: int = 2):
        self.limit, self.in_a_row = limit, 0

    def saw(self, failure: Failure | None) -> None:
        self.in_a_row = self.in_a_row + 1 if failure and failure.kind == "network" else 0
        if self.in_a_row >= self.limit:
            raise NetworkDown
