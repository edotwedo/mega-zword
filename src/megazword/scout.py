"""Scout for new free AI providers and models."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen
from typing import List, Dict, Any

from . import config
from .free_apis import FREE_KEYS

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
        # A missing price is unknown, not free.
        costs = model_info.get("input_cost_per_token"), model_info.get("output_cost_per_token")
        if None not in costs and costs == (0, 0):
            provider = model_info.get("litellm_provider")
            if isinstance(provider, str) and provider.strip():
                results.append({
                    "provider": provider.strip(),
                    "model": model_name
                })
    return sorted(results, key=lambda x: (x["provider"], x["model"]))



# Provider names that don't match their key name.
ALIASES = {"google": ("google", "gemini", "vertex"), "tencent": ("tencent", "hunyuan")}


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def known_families() -> set:
    """Providers Mega Zword already has a key for, from the key names (GROQ_API_KEY -> groq)."""
    found = set()
    for _, key in FREE_KEYS:
        family = key.split("_")[0].lower()
        found.update(ALIASES.get(family, (family,)))
    return found


def leads(sources: Dict[str, List[str]], previous: List[Dict[str, Any]] | None = None,
          today: str | None = None, known: set | None = None) -> List[Dict[str, Any]]:
    """Merge provider names from each source into one list of leads.

    sources maps a source name ("openrouter", "litellm") to provider names. A
    provider seen before keeps its first_seen date. New providers sort first.
    """
    today = today or date.today().isoformat()
    known = known_families() if known is None else known
    old = {_norm(row["provider"]): row for row in previous or []}
    rows: Dict[str, Dict[str, Any]] = {}
    for source, names in sources.items():
        for name in names:
            key = _norm(name)
            if not key:
                continue
            row = rows.setdefault(key, {
                "provider": old.get(key, {}).get("provider", name.strip()),
                "seen_in": [],
                "already_have": any(key.startswith(family) for family in known),
                "first_seen": old.get(key, {}).get("first_seen", today),
            })
            if source not in row["seen_in"]:
                row["seen_in"].append(source)
    for row in rows.values():
        row["seen_in"].sort()
        row["new"] = _norm(row["provider"]) not in old
    return sorted(rows.values(), key=lambda r: (not r["new"], r["already_have"], r["provider"].lower()))


def leads_path() -> Path:
    return config.HOME / "scout" / "leads.json"


def update_leads(sources: Dict[str, List[str]], path: Path | None = None,
                 today: str | None = None) -> List[Dict[str, Any]]:
    """Merge sources into the saved leads file and return the merged rows."""
    path = path or leads_path()
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = []
    rows = leads(sources, previous if isinstance(previous, list) else [], today)
    # Keep providers this run didn't see, so first_seen survives a source being down.
    seen = {_norm(r["provider"]) for r in rows}
    kept = [dict(r, new=False) for r in previous if isinstance(r, dict)
            and r.get("provider") and _norm(r["provider"]) not in seen]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows + kept, indent=2), encoding="utf-8")
    return rows + kept
