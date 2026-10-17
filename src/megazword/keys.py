"""Keymaster: names and status are public; credential values stay local."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from . import credential_store as vault


def key_names() -> tuple[str, ...]:
    from .free_apis import FREE_KEYS
    return tuple(dict.fromkeys([name for _, name in FREE_KEYS] + ["CLOUDFLARE_ACCOUNT_ID"]))


def get_key(env_name: str) -> str | None:
    value = os.environ.get(env_name)
    if value:
        return value
    try:
        return vault.read(env_name)
    except vault.VaultError:
        return None


def _secret_values() -> list[str]:
    """Every credential value from the environment and the vault, longest first."""
    values = {value for name, value in os.environ.items()
              if value and re.search(r"KEY|TOKEN|SECRET|PASSWORD|ACCOUNT_ID", name, re.I)}
    for name in key_names():
        try:
            value = vault.read(name)
        except vault.VaultError:
            continue
        if value:
            values.add(value)
    return sorted(values, key=len, reverse=True)


def redact_known(text: str, mask: str = "[REDACTED]", values: list[str] | None = None) -> str:
    """Also scrub vault copies shadowed by environment overrides."""
    for value in _secret_values() if values is None else values:
        text = text.replace(value, mask)
    return text


def redact_payload(value, _values: list[str] | None = None):
    """Preserve message structure while scrubbing strings before JSON encoding.

    The vault is read once per payload, not once per string (Greptile, PR #59):
    a chat turn has many strings and each vault read is a Credential Manager call.
    """
    values = _secret_values() if _values is None else _values
    if isinstance(value, str):
        return redact_known(value, values=values)
    if isinstance(value, list):
        return [redact_payload(item, values) for item in value]
    if isinstance(value, dict):
        return {key: redact_payload(item, values) for key, item in value.items()}
    return value


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _probe(backend) -> str:
    """One metadata GET, no inference, retry, response text or redirects."""
    key = get_key(backend.key_env)
    if not key:
        return "no answer"
    url = backend.base_url.rstrip("/") + "/models"
    headers = {"Authorization": "Bearer " + key}
    if backend.key_env == "OPENROUTER_API_KEY":
        # The public model catalog does not validate a key.
        url = "https://openrouter.ai/api/v1/key"
    elif backend.key_env == "GOOGLE_AI_API_KEY":
        url = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1"
        headers = {"x-goog-api-key": key}
    elif backend.key_env == "CLOUDFLARE_API_TOKEN":
        account = get_key("CLOUDFLARE_ACCOUNT_ID")
        if not account or not re.fullmatch(r"[a-fA-F0-9]{32}", account):
            return "no answer"
        url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/models/search?per_page=1"
    try:
        request = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=10) as response:
            if response.status != 200:
                return "no answer"
            # Check the provider's envelope without retaining/printing metadata.
            payload = json.loads(response.read(65536))
            if not isinstance(payload, dict) or payload.get("success") is False:
                return "no answer"
            if "data" not in payload and "models" not in payload and "result" not in payload:
                return "no answer"
        return "ok"
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        if code in (401, 403):
            return f"rejected ({code})"
        return "rate limited" if code == 429 else "no answer"
    except Exception:
        # URLs, header values and server exception text are deliberately private.
        return "no answer"


def show() -> int:
    from .free_apis import free_backends
    providers = {}
    for backend in free_backends({}):
        providers.setdefault(backend.key_env, backend)
    results = {}
    print(f"{'key':<28} {'source':<9} check")
    for name in key_names():
        try:
            source = "env" if os.environ.get(name) else "vault" if vault.read(name) else "missing"
        except vault.VaultError:
            print(f"{name:<28} {'unknown':<9} no answer (vault unavailable)")
            continue
        provider_key = "CLOUDFLARE_API_TOKEN" if name == "CLOUDFLARE_ACCOUNT_ID" else name
        if source == "missing":
            result = "no answer"
        else:
            if provider_key not in results:
                results[provider_key] = _probe(providers[provider_key])
            result = results[provider_key]
        print(f"{name:<28} {source:<9} {result}")
    print("Checks use metadata only; ok does not prove inference access or free quota.")
    return 0


def move() -> int:
    from .config import _windows_user_env
    if not vault.available():
        print("Credential Manager unavailable; environment copies unchanged.")
        return 1
    failed = False
    moved = False
    for name in key_names():
        try:
            saved = _windows_user_env(name)
            current = os.environ.get(name)
            if saved and current and saved != current:
                print(f"{name}: process and user environment differ; skipped.")
                failed = True
                continue
            value = saved or current
            if not value:
                continue
            vault.write(name, value)
            if vault.read(name) != value:
                raise vault.VaultError("Credential verification failed")
        except Exception:
            print(f"{name}: move failed; environment copy unchanged.")
            failed = True
            continue
        moved = True
        print(f"{name}: copied and verified; environment copy unchanged.")
        # setx NAME "" is unreliable for deleting variables; print an exact
        # PowerShell command instead. Names are a fixed application allowlist.
        print(f"[Environment]::SetEnvironmentVariable('{name}', $null, 'User')")
    if moved:
        print("Optional: run the printed PowerShell lines, then restart apps/shells to drop inherited copies.")
    elif not failed:
        print("No environment keys to move.")
    return 1 if failed else 0


def command(action: str = "show") -> int:
    return move() if action == "move" else show()
