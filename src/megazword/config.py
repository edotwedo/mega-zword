"""Settings. Defaults live here; override them in ~/.megazword/config.toml.

Example config.toml:

    rater_model = "qwen2.5:1.5b"

    [route]
    easy = ["grok", "codex", "claude"]
    medium = ["codex", "claude", "grok"]
    hard = ["claude", "codex", "grok"]

    # Mark an AI as out of usage until a date or time; auto-pick skips it.
    [out]
    grok = 2026-10-17T23:30:00-07:00

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
from datetime import date, datetime, timezone
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
    # AI name -> when its usage comes back. Set by hand for plans with no meter.
    out_until: dict[str, datetime] = field(default_factory=dict)

    def out_now(self, now: datetime | None = None) -> set[str]:
        """AIs marked out whose return time hasn't passed yet."""
        now = now or datetime.now(timezone.utc)
        return {name for name, until in self.out_until.items() if until > now}


def _as_time(value) -> datetime:
    """TOML date, local datetime, offset datetime or ISO string -> aware datetime.
    A bare date means the start of that day, local time."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime) and isinstance(value, date):
        value = datetime(value.year, value.month, value.day)
    return value if value.tzinfo else value.astimezone()


def load(path: Path = HOME / "config.toml") -> Config:
    cfg = Config()
    if path.exists():
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        cfg.rater_model = data.get("rater_model", cfg.rater_model)
        cfg.route.update(data.get("route", {}))
        cfg.out_until = {name: _as_time(v) for name, v in data.get("out", {}).items()}

        for level, block in data.get("grok", {}).items():
            if isinstance(block, dict) and level in cfg.grok:
                model, effort = cfg.grok[level]
                cfg.grok[level] = (str(block.get("model", model)),
                                   str(block.get("effort", effort)))
    return cfg


def render_default(installed: list[str]) -> str:
    """Render a commented config with only installed AIs in each route."""
    lines = ["# Local model used to rate each prompt's difficulty.",
             'rater_model = "qwen2.5:1.5b"', "", "# AIs to try, from first choice to last.", "[route]"]
    for level, names in DEFAULT_ROUTE.items():
        choices = [name for name in names if name in installed]
        values = ", ".join(f'"{name}"' for name in choices)
        lines.extend([f"# AIs to try for {level} tasks, in order.", f"{level} = [{values}]"])
    return "\n".join(lines) + "\n"


def write_default(path: Path, installed: list[str], force: bool = False) -> None:
    """Write the default config, refusing to replace an existing file."""
    if path.exists() and not force:
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_default(installed), encoding="utf-8")
