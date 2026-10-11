"""Settings. Defaults live here; override them in ~/.megazword/config.toml.

Example config.toml:

    rater_model = "qwen2.5:1.5b"

    [route]
    easy = ["grok", "codex", "claude"]
    medium = ["codex", "claude", "grok"]
    hard = ["claude", "codex", "grok"]

    [grok.easy]
    model = "grok-4.6"
    effort = "low"
    [grok.medium]
    model = "grok-4.6"
    effort = "medium"
    [grok.hard]
    model = "grok-4.7"
    effort = "high"
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

HOME = Path(os.environ.get("MEGAZWORD_HOME", Path.home() / ".megazword"))

DEFAULT_GROK = {
    # easy = status-sized; medium = coding; hard = design. Phil, 2026-10-10.
    "easy": ("grok-4.6", "low"),
    "medium": ("grok-4.6", "medium"),
    "hard": ("grok-4.7", "high"),
}

DEFAULT_ROUTE = {
    # First installed AI in each list wins. Placeholder order until usage
    # tracking (build step 2) can rank them by remaining usage.
    "easy": ["grok", "codex", "claude"],
    "medium": ["codex", "claude", "grok"],
    "hard": ["claude", "codex", "grok"],
}


@dataclass
class Config:
    rater_model: str = "qwen2.5:1.5b"
    route: dict[str, list[str]] = field(default_factory=lambda: dict(DEFAULT_ROUTE))
    grok: dict[str, tuple[str, str]] = field(default_factory=lambda: dict(DEFAULT_GROK))
    log_path: Path = HOME / "log.jsonl"


def load(path: Path = HOME / "config.toml") -> Config:
    cfg = Config()
    if path.exists():
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        cfg.rater_model = data.get("rater_model", cfg.rater_model)
        cfg.route.update(data.get("route", {}))
        for level, block in data.get("grok", {}).items():
            if isinstance(block, dict) and level in cfg.grok:
                model, effort = cfg.grok[level]
                cfg.grok[level] = (str(block.get("model", model)),
                                   str(block.get("effort", effort)))
    return cfg
