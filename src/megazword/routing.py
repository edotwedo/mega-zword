"""Small route-order policies shared by chat, coding and parallel jobs."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

TENCENT_BACKENDS = (
    "tencent-glm-5.3-flash",
    "tencent-glm-5.3",
    "tencent-kimi-k2.7-code",
    "tencent-kimi-k3",
)


def tencent_first(names: list[str], log_path: Path | None = None) -> list[str]:
    """Lead with Tencent's free-trial models, favoring the least-used one.

    Mega Zword's local run log only estimates token use. Tencent remains the
    source of truth for each service's actual free-quota balance.
    """
    group = [name for name in names if name in TENCENT_BACKENDS]
    if not group:
        return list(names)

    if log_path is None:
        from .config import HOME
        log_path = HOME / "log.jsonl"
    from .runlog import summarize

    usage = summarize(log_path, timedelta(days=365)) if len(group) > 1 else {}
    position = {name: index for index, name in enumerate(group)}
    group.sort(key=lambda name: (
        usage.get(name).est_tokens if usage.get(name) else 0,
        position[name],
    ))
    return [*group, *(name for name in names if name not in TENCENT_BACKENDS)]
