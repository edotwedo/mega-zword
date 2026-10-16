"""Scout for new free AI providers and models."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import List, Dict, Any

TIMEOUT_SECONDS = 15


def providers_from_endpoints(payload: Dict[str, Any]) -> List[str]:
    """Extract unique provider names from OpenRouter model endpoints payload.

    Expected payload shape: {"data": {"endpoints": [{"provider_name": str, ...}]}}
    Returns sorted list of unique provider names.
    """
    data = payload.get("data", {})
    if not isinstance(data, dict):
        return []
    endpoints = data.get("endpoints", [])
    if not isinstance(endpoints, list):
        return []
    providers = []
    for ep in endpoints:
        if isinstance(ep, dict):
            provider = ep.get("provider_name")
            if isinstance(provider, str) and provider.strip():
                providers.append(provider.strip())
    return sorted(set(providers))


def fetch_endpoints(model_id: str) -> Dict[str, Any]:
    """Fetch endpoints for a given model from OpenRouter API.

    Returns the parsed JSON response.
    """
    url = f"https://openrouter.ai/api/v1/models/{model_id}/endpoints"
    request = Request(url, headers={"User-Agent": "megazword/0.1.0b1"})
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.load(response)

