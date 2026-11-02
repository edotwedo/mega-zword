"""Read OpenRouter's public catalog for current free tool-capable models."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import __version__


CATALOG_URL = "https://openrouter.ai/api/v1/models"
TIMEOUT_SECONDS = 15


def _zero_price(value) -> bool:
    try:
        return Decimal(str(value)) == 0
    except (InvalidOperation, ValueError, TypeError):
        return False


def free_tool_models(payload: dict) -> list[dict]:
    """Select models whose catalog metadata advertises zero cost and tools."""
    data = payload.get("data", []) if isinstance(payload, dict) else []
    found = []
    for model in data:
        if not isinstance(model, dict):
            continue
        model_id = model.get("id")
        pricing = model.get("pricing")
        params = model.get("supported_parameters")
        if (not isinstance(model_id, str) or not isinstance(pricing, dict)
                or not isinstance(params, list) or "tools" not in params
                or not _zero_price(pricing.get("prompt"))
                or not _zero_price(pricing.get("completion"))):
            continue
        found.append({
            "id": model_id,
            "name": str(model.get("name") or model_id),
            "context_length": model.get("context_length"),
        })
    return sorted(found, key=lambda item: item["id"].casefold())


def fetch_catalog() -> dict:
    request = Request(CATALOG_URL, headers={"User-Agent": f"megazword/{__version__}"})
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.load(response)


def command() -> int:
    try:
        models = free_tool_models(fetch_catalog())
    except HTTPError as exc:
        print(f"OpenRouter catalog request failed: HTTP {exc.code}.", file=sys.stderr)
        return 1
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        reason = "network or invalid JSON response"
        if isinstance(exc, URLError) and isinstance(exc.reason, str):
            reason = " ".join(exc.reason.split())[:120]
        print(f"OpenRouter catalog request failed: {reason}.", file=sys.stderr)
        return 1

    if not models:
        print("No zero-priced models with tool support found in the current catalog.")
        return 0

    print("Current OpenRouter models (catalog says $0 and supports tools):")
    for model in models:
        context = model["context_length"]
        context_text = f"{context:,}" if isinstance(context, int) else "?"
        print(f"{model['id']}\t{context_text} tokens\t{model['name']}")
    print("Catalog only: endpoints can still be throttled or app-restricted; test before relying on them.")
    return 0
