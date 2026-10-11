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
import re
import tomllib
from datetime import date, datetime, timedelta, timezone
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
    # Looked up when a Config is made (not at import) so tests can redirect HOME.
    log_path: Path = field(default_factory=lambda: HOME / "log.jsonl")
    # How many lines log.jsonl and each project's memory.jsonl keep ([limits]).
    log_lines: int = 5000
    memory_lines: int = 2000
    # AI name -> seconds to wait for an answer before giving up on it.
    timeouts: dict[str, int] = field(default_factory=dict)
    # Second-opinion check on auto-picked answers (local model). Off by default.
    quality_check: bool = False
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


def load(path: Path | None = None) -> Config:
    path = path if path is not None else HOME / "config.toml"
    cfg = Config()
    if path.exists():
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        cfg.rater_model = data.get("rater_model", cfg.rater_model)
        cfg.route.update(data.get("route", {}))
        cfg.quality_check = bool(data.get("quality_check", cfg.quality_check))
        cfg.out_until = {name: _as_time(v) for name, v in data.get("out", {}).items()}
        limits = data.get("limits", {})
        for key in ("log_lines", "memory_lines"):
            if isinstance(limits.get(key), int) and limits[key] > 0:
                setattr(cfg, key, limits[key])
        cfg.timeouts = {name: int(v) for name, v in data.get("timeouts", {}).items()
                        if isinstance(v, (int, float)) and v > 0}

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


# --- editing [out] from the CLI / dashboard ------------------------------

_KEY = re.compile(r"^\s*([A-Za-z0-9_-]+)\s*=")


def parse_until(text: str, now: datetime | None = None) -> datetime:
    """'7d', '5h', '30m', '2026-10-17' or '2026-10-17T23:30' -> aware datetime."""
    now = now or datetime.now(timezone.utc)
    m = re.fullmatch(r"(\d+)\s*([dhm])", text.strip().lower())
    if m:
        n, unit = int(m.group(1)), m.group(2)
        return now + {"d": timedelta(days=n), "h": timedelta(hours=n),
                      "m": timedelta(minutes=n)}[unit]
    return _as_time(text.strip())


def set_out(path: Path, name: str, until: datetime | None) -> None:
    """Set (or with until=None, remove) one AI's line in the [out] table of
    config.toml. Only that line changes; comments and other tables stay."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise ValueError(f"bad AI name {name!r}")
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    value = f"{name} = {until.isoformat(timespec='seconds')}" if until else None

    start = next((i for i, l in enumerate(lines) if l.strip() == "[out]"), None)
    if start is None:
        if value:
            if lines and lines[-1].strip():
                lines.append("")
            lines += ["# AIs out of usage until a date or time; auto-pick skips them.",
                      "[out]", value]
    else:
        end = next((i for i in range(start + 1, len(lines))
                    if lines[i].lstrip().startswith("[")), len(lines))
        hit = next((i for i in range(start + 1, end)
                    if (m := _KEY.match(lines[i])) and m.group(1) == name), None)
        if hit is not None:
            if value:
                lines[hit] = value
            else:
                del lines[hit]
        elif value:
            last = max((i for i in range(start, end) if lines[i].strip()), default=start)
            lines.insert(last + 1, value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    load(path)  # fail loudly now rather than on the next run
