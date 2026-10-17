"""Small route-order policies shared by chat, coding and parallel jobs."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

TENCENT_BACKENDS = (
    "tencent-glm-5.3-flash",
    "tencent-glm-5.3",
    "tencent-kimi-k2.7-code",
    "tencent-kimi-k3",
    "tencent-deepseek-v4-pro",
    "tencent-deepseek-v4-flash-vision-exp",
)

# Paid subscription CLIs keep their configured order after every free source.
PAID_BACKENDS = ("claude", "codex", "grok", "gemini")
# Cheap paid OpenRouter models under budget.MONTHLY_USD: after every free
# source, before the paid CLIs. Pro first on hard work, Flash first otherwise.
CHEAP_PREFIX = "cheap-"

# One-time grants that never refill. Outside hard work each request counts four
# times, so they get roughly a quarter share next to free tiers that reset.
FINITE_BACKENDS = TENCENT_BACKENDS
FINITE_SHARE = 0.25

SPREAD_WINDOW = timedelta(hours=24)

# Small models (3B-8B) share easy work; for medium and hard work they only go
# after every stronger free source.
WEAK_BACKENDS = ("mistral", "groq-allam", "nvidia", "ollama",
                 "openrouter-nemotron-nano", "openrouter-laguna-xs")


def spread(names: list[str], level: str = "medium",
           log_path: Path | None = None, coding: bool = False) -> list[str]:
    """Order free sources so the least-used one in the last 24 hours goes first.

    Phil (2026-10-16): use a tiny bit of every free source instead of draining
    one before moving to the next. Hard work leads with the finite Tencent grants
    (the strongest free coders), spread among themselves. Ties keep the
    configured order. Mega Zword's run log only estimates use; each provider's
    console stays the source of truth for balances.
    """
    names = list(dict.fromkeys(names))
    cheap = sorted((n for n in names if n.startswith(CHEAP_PREFIX)),
                   key=lambda n: ("pro" not in n) if level == "hard" else ("pro" in n))
    free = [name for name in names if name not in PAID_BACKENDS and name not in cheap]
    paid = [*cheap, *(name for name in names if name in PAID_BACKENDS)]
    if not free:
        return paid

    if log_path is None:
        from .config import HOME
        log_path = HOME / "log.jsonl"
    from .runlog import summarize

    # Hard block (ledger): never route to a source that could bill, or to a
    # grant that is used up or expired.
    from .ledger import blocked
    stop = blocked(free, home=log_path.parent, log_path=log_path)
    free = [name for name in free if name not in stop]

    usage = summarize(log_path, SPREAD_WINDOW)
    from .free_apis import KEYLESS
    position = {name: index for index, name in enumerate(free)}

    def load(name: str) -> float:
        runs = usage[name].runs if name in usage else 0
        if name in FINITE_BACKENDS and level != "hard":
            return runs / FINITE_SHARE
        return float(runs)

    def key(name: str):
        finite = name in FINITE_BACKENDS
        lead = 0 if level == "hard" and finite else 1
        # On a tie outside hard work, free tiers that reset go before grants.
        weak = name in WEAK_BACKENDS and level != "easy"
        # Keyless sources wait 18-31 s between calls: fine for one answer, but a
        # 50-step coding loop on them can outrun a 30-minute job. They code last.
        slow = coding and name in KEYLESS
        return (lead, weak, slow, load(name), finite and level != "hard", position[name])

    return [*sorted(free, key=key), *paid]
