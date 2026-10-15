"""One-shot health checks for configured free providers."""

from __future__ import annotations

import os
import re

from .backends import Backend, OllamaBackend

PROVIDERS = (
    "groq", "gemini-api", "mistral", "cloudflare", "openrouter", "kimi",
    "deepseek", "qwen-coder", "nvidia", "zai", "ollama",
)
PROMPT = "Reply with: ok"
TIMEOUT_SECONDS = 30


def _safe_reason(reason: str) -> str:
    from .guard import scrub

    for name, value in sorted(os.environ.items(), key=lambda item: -len(item[1])):
        if value and ("KEY" in name.upper() or "TOKEN" in name.upper()
                      or "SECRET" in name.upper() or "PASSWORD" in name.upper()
                      or name == "CLOUDFLARE_ACCOUNT_ID"):
            reason = reason.replace(value, "[REDACTED]")
    reason = re.sub(r"https?://\S+|Bearer\s+\S+", "[REDACTED]", reason, flags=re.I)
    reason = " ".join(scrub(reason).split())
    return reason[:160] or "request failed"


def command(backends: dict[str, Backend], free_models: dict[str, str]) -> int:
    """Probe only configured APIs and a reachable local Ollama server."""
    ollama = OllamaBackend("ollama", model=free_models.get("ollama", "qwen2.5-coder:7b"))
    providers = {**backends, "ollama": ollama}
    rows: list[tuple[str, bool, float, str]] = []

    for name in PROVIDERS:
        backend = providers.get(name)
        if backend is None or not backend.available():
            continue
        backend.timeout = min(backend.timeout, TIMEOUT_SECONDS)
        result = backend.run(PROMPT)
        rows.append((name, result.ok, result.seconds, "" if result.ok else _safe_reason(result.error)))

    print(f"{'provider':<14} {'status':<8} {'seconds':>7}  reason")
    print("-" * 58)
    for name, ok, seconds, reason in rows:
        print(f"{name:<14} {'ok' if ok else 'failed':<8} {seconds:>7.1f}  {reason}")
    if not rows:
        print("No configured free providers found.")
        return 0
    return 0 if all(ok for _, ok, _, _ in rows) else 1
