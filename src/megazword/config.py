"""Settings. Defaults live here; override them in ~/.megazword/config.toml.

Example config.toml:

    rater_model = "qwen2.5:1.5b"

    [route]
    easy = ["grok", "codex", "claude"]
    medium = ["codex", "claude", "grok"]
    hard = ["claude", "codex", "grok"]
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

HOME = Path(os.environ.get("MEGAZWORD_HOME", Path.home() / ".megazword"))

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
    log_path: Path = HOME / "log.jsonl"


def load(path: Path = HOME / "config.toml") -> Config:
    cfg = Config()
    if path.exists():
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        cfg.rater_model = data.get("rater_model", cfg.rater_model)
        cfg.route.update(data.get("route", {}))
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
