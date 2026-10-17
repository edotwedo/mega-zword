"""One-shot health checks for configured free providers."""

from __future__ import annotations

import os
import re

from .backends import Backend, OllamaBackend
from . import openrouter_catalog

OPENROUTER_PROVIDERS = {"openrouter", "kimi", "deepseek", "qwen-coder",
                        "openrouter-dots", "openrouter-nemotron-nano",
                        "openrouter-nemotron-lightning", "openrouter-laguna-s",
                        "openrouter-laguna-xs"}

PROVIDERS = (
    "groq", "groq-120b", "groq-qwen", "groq-allam", "gemini-api",
    "gemini-api-31-lite", "gemini",
    "mistral", "cloudflare", "openrouter", "kimi",
    "deepseek", "qwen-coder", "openrouter-dots", "openrouter-nemotron-nano",
    "openrouter-nemotron-lightning", "openrouter-laguna-s", "openrouter-laguna-xs",
    "nvidia", "nvidia-lightning", "zai", "zai-47", "ovh",
    "tencent-glm-5.3-flash", "tencent-glm-5.3",
    "tencent-kimi-k2.7-code", "tencent-kimi-k3",
    "tencent-deepseek-v4-pro", "tencent-deepseek-v4-flash-vision-exp",
    "ollama",
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


def command(backends: dict[str, Backend], free_models: dict[str, str],
            selected: list[str] | None = None, out: set[str] | None = None) -> int:
    """Probe selected free identities; out-marked providers are never called."""
    ollama = OllamaBackend("ollama", model=free_models.get("ollama", "qwen2.5-coder:7b"))
    providers = {**backends, "ollama": ollama}
    names = list(dict.fromkeys(PROVIDERS if selected is None else selected))
    out = out or set()
    rows: list[tuple[str, bool | None, float, str]] = []
    explicitly_selected_failure = False

    candidates = [providers.get(name) for name in names if name in OPENROUTER_PROVIDERS]
    candidates = [backend for backend in candidates if backend is not None
                  and backend.available() and callable(getattr(backend, "chat", None))]
    allowed_openrouter_models = None
    catalog_error = ""
    if candidates:
        try:
            allowed_openrouter_models = {
                item["id"] for item in
                openrouter_catalog.free_tool_models(openrouter_catalog.fetch_catalog())
            }
        except (OSError, TimeoutError, ValueError):
            catalog_error = "current free catalog unavailable; skipped to avoid an unverified charge"

    for name in names:
        if name in out:
            rows.append((name, None, 0, "marked out; skipped"))
            continue
        backend = providers.get(name)
        if backend is None or not backend.available():
            if selected is not None:
                explicitly_selected_failure = True
                rows.append((name, None, 0, "not configured or unavailable"))
            continue
        if name in OPENROUTER_PROVIDERS and callable(getattr(backend, "chat", None)):
            model = getattr(backend, "model", "")
            if catalog_error or model not in (allowed_openrouter_models or set()):
                explicitly_selected_failure = explicitly_selected_failure or selected is not None
                reason = catalog_error or "model is not verified as free and tool-capable in the current catalog"
                rows.append((name, False, 0, reason))
                continue
        timeout = 180 if name.startswith("tencent-") else TIMEOUT_SECONDS
        backend.timeout = min(backend.timeout, timeout)
        result = backend.run(PROMPT)
        rows.append((name, result.ok, result.seconds, "" if result.ok else _safe_reason(result.error)))

    print(f"{'provider':<14} {'status':<8} {'seconds':>7}  reason")
    print("-" * 58)
    for name, ok, seconds, reason in rows:
        status = "ok" if ok is True else "failed" if ok is False else "skipped"
        print(f"{name:<14} {status:<8} {seconds:>7.1f}  {reason}")
    if not rows:
        print("No configured free providers found.")
        return 0
    return 0 if not explicitly_selected_failure and all(
        ok is not False for _, ok, _, _ in rows) else 1
