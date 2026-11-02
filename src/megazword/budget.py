"""Monthly cap for cheap paid models on OpenRouter (Phil, 2026-10-17).

Phil allowed $1 a month of very cheap paid tokens (DeepSeek V4 Flash/Pro, about
4-10M tokens per dollar). Spend is read from OpenRouter's key endpoint before
every paid call, so the cap holds across processes. Anything unknown fails
closed: no reading means no paid call.
"""

from __future__ import annotations

import json
import time
import urllib.request

from . import config, __version__
from .filelock import write_atomic
from .keys import get_key

MONTHLY_USD = 1.00     # default cap; override with ~/.megazword/budget.json {"monthly_usd": N}
MARGIN_USD = 0.02      # stop a little early: one call can cost about a cent
CACHE_SECONDS = 20
KEY_URL = "https://openrouter.ai/api/v1/key"


def _path():
    return config.HOME / "budget.json"


def _load() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def cap() -> float:
    try:
        return max(0.0, float(_load().get("monthly_usd", MONTHLY_USD)))
    except (TypeError, ValueError):
        return 0.0


def _fetch_spend() -> float:
    key = get_key("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    request = urllib.request.Request(KEY_URL, headers={
        "Authorization": f"Bearer {key}", "User-Agent": f"megazword/{__version__}"})
    with urllib.request.urlopen(request, timeout=15) as response:
        data = json.load(response).get("data", {})
    return float(data["usage_monthly"])


def spend(fetch=None) -> float:
    """This month's OpenRouter spend in USD, cached briefly."""
    data = _load()
    if time.time() - data.get("checked", 0) < CACHE_SECONDS and "spend" in data:
        return float(data["spend"])
    value = (fetch or _fetch_spend)()
    data.update(spend=value, checked=time.time())
    _path().parent.mkdir(parents=True, exist_ok=True)
    write_atomic(_path(), json.dumps(data))
    return value


def room(fetch=None) -> tuple[bool, str]:
    """(may spend, why). Fails closed on any error."""
    limit = cap()
    try:
        used = spend(fetch)
    except Exception as exc:  # network, key, bad reply: no paid call
        return False, f"cheap paid budget unknown ({type(exc).__name__}); not calling"
    if used >= limit - MARGIN_USD:
        return False, f"cheap paid budget reached (${used:.2f} of ${limit:.2f} this month)"
    return True, f"${used:.2f} of ${limit:.2f} this month"


def known_exhausted() -> bool:
    """From the last saved reading only (no network), for quick availability checks."""
    data = _load()
    return "spend" in data and float(data["spend"]) >= cap() - MARGIN_USD


def line() -> str:
    data = _load()
    if "spend" not in data:
        return f"Cheap paid (OpenRouter): cap ${cap():.2f}/month, no spend reading yet"
    return f"Cheap paid (OpenRouter): ${float(data['spend']):.2f} of ${cap():.2f} this month"
