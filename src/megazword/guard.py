"""B15's one light guard: before a prompt goes to an AI that trains on what we send
(Mistral free tier, Gemini API unpaid), blank out obvious secrets and private paths.
Phil chose the lightest rules (2026-10-11); this is the only check they keep."""

from __future__ import annotations

import re

MASK = "[removed by Mega Zword]"

_PATTERNS = [
    # private key blocks
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    # well-known token shapes
    re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}"),  # JWTs
    # env-style NAME_KEY=value anywhere in a line
    re.compile(r"\b[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASS)[A-Z0-9_]*=\S+"),
]
# KEY=value / password: value, as in .env files and configs
_ASSIGN = re.compile(
    r"(?im)^(\s*[\w.-]*(?:pass(?:word|wd)?|secret|token|api[_-]?key|private[_-]?key|credential)s?"
    r"[\w.-]*\s*[=:]\s*)(\S+)\s*$")
# files under the AIs' own login folders or Phil's private folders
_PRIVATE = re.compile(r"(?i)[^\s'\"]*[\\/](?:\.claude|\.codex|\.grok|\.megazword|private)[\\/][^\s'\"]*")


def scrub(text: str) -> str:
    """The prompt with secrets and private paths replaced by MASK."""
    for pattern in _PATTERNS:
        text = pattern.sub(MASK, text)
    text = _ASSIGN.sub(lambda m: m.group(1) + MASK, text)
    return _PRIVATE.sub(MASK, text)
