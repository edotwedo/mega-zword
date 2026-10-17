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


def zero_price_litellm(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    """Parse LiteLLM's public price file and return zero-cost entries.
    
    Returns list of {"provider": str, "model": str} for entries where both
    input_cost_per_token and output_cost_per_token are 0. Skips sample_spec
    and entries without costs.
    """
    results = []
    for model_name, model_info in payload.items():
        if not isinstance(model_info, dict):
            continue
        if model_name == "sample_spec":
            continue
        costs = model_info.get("input_cost_per_token", 0), model_info.get("output_cost_per_token", 0)
        if costs == (0, 0):
            provider = model_info.get("litellm_provider")
            if isinstance(provider, str) and provider.strip():
                results.append({
                    "provider": provider.strip(),
                    "model": model_name
                })
    return sorted(results, key=lambda x: (x["provider"], x["model"]))

