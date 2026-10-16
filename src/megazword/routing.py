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

# One-time grants that never refill. Outside hard work each request counts four
# times, so they get roughly a quarter share next to free tiers that reset.
FINITE_BACKENDS = TENCENT_BACKENDS
FINITE_SHARE = 0.25

SPREAD_WINDOW = timedelta(hours=24)


def spread(names: list[str], level: str = "medium",
           log_path: Path | None = None) -> list[str]:
    """Order free sources so the least-used one in the last 24 hours goes first.

    Phil (2026-10-16): use a tiny bit of every free source instead of draining
    one before moving to the next. Hard work leads with the finite Tencent grants
    (the strongest free coders), spread among themselves. Ties keep the
    configured order. Mega Zword's run log only estimates use; each provider's
    console stays the source of truth for balances.
    """
    names = list(dict.fromkeys(names))
    free = [name for name in names if name not in PAID_BACKENDS]
    paid = [name for name in names if name in PAID_BACKENDS]
    if len(free) < 2:
        return [*free, *paid]

    if log_path is None:
        from .config import HOME
        log_path = HOME / "log.jsonl"
    from .runlog import summarize

    usage = summarize(log_path, SPREAD_WINDOW)
    position = {name: index for index, name in enumerate(free)}

    def load(name: str) -> float:
        runs = usage[name].runs if name in usage else 0
        if name in FINITE_BACKENDS and level != "hard":
            return runs / FINITE_SHARE
        return float(runs)

    def key(name: str):
        lead = 0 if level == "hard" and name in FINITE_BACKENDS else 1
        return (lead, load(name), position[name])

    return [*sorted(free, key=key), *paid]
