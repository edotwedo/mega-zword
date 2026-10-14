"""One prompt per configured free API, without routing or retries."""

import os
import re
from dataclasses import replace

from .backends import OllamaBackend
from .free_apis import FREE_KEYS, free_backends
from .guard import scrub


def _reason(error):
    for name, value in sorted(os.environ.items(), key=lambda item: -len(item[1])):
        if value and (re.search(r"KEY|TOKEN|SECRET|PASSWORD", name, re.I)
                      or name == "CLOUDFLARE_ACCOUNT_ID"):
            error = error.replace(value, "[REDACTED]")
    error = re.sub(r"https?://\S+|Bearer\s+\S+", "[REDACTED]", error, flags=re.I)
    return " ".join(scrub(error).split())[:120]


def run(cfg, backends=None):
    if backends is None:
        backends = {b.name: b for b in free_backends(cfg.free)}
        backends["ollama"] = OllamaBackend(
            "ollama", model=cfg.free.get("ollama", "qwen2.5-coder:7b"))
    print(f"{'name':<12} {'status':<6} {'seconds':>7}  error")
    failed = False
    for name, key in (*FREE_KEYS, ("ollama", "")):
        if name not in backends or (key and not os.environ.get(key)):
            continue
        backend = replace(backends[name], timeout=min(backends[name].timeout, 30))
        result = backend.run("Reply with: ok")
        ok = result.ok and bool(result.text.strip())
        reason = "" if ok else _reason(result.error or "Empty response")
        print(f"{name:<12} {'ok' if ok else 'failed':<6} {result.seconds:>7.2f}  {reason}")
        failed |= not ok
    return int(failed)
