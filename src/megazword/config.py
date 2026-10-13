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

    # Same idea for Claude, Codex and Gemini (agy). Leave one out to keep
    # that CLI's own default model and effort.
    [claude.hard]
    model = "opus"
    effort = "high"
    [codex.easy]
    effort = "low"
"""

from __future__ import annotations

import os
import json
import tempfile
import threading
from copy import deepcopy
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
    # Mistral first for small repetitive jobs (B15, Phil 2026-10-11); it is only
    # used when MISTRAL_API_KEY is set.
    "easy": ["mistral", "grok", "codex", "claude"],
    "medium": ["codex", "claude", "grok"],
    "hard": ["claude", "codex", "grok"],
}

DEFAULT_FREE = {
    "ollama": "qwen2.5-coder:7b",
    "openrouter": "qwen/qwen3-4b:free",
    "groq": "llama-3.3-70b-versatile",
    "cloudflare": "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    "zai": "glm-4.5-flash",
    "gemini-api": "gemini-flash-latest",
    "nvidia": "meta/llama-3.1-8b-instruct",
    "mistral": "mistral-small-latest",
}

# API keys Mega Zword reads. On Windows a key set with
# SetEnvironmentVariable(..., "User") is missing from shells and subprocesses
# started before it was set, so load_user_env() fills these in from the registry.
USER_ENV_KEYS = (
    "GROQ_API_KEY", "OPENROUTER_API_KEY", "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_ACCOUNT_ID", "ZAI_API_KEY", "GOOGLE_AI_API_KEY",
    "NVIDIA_API_KEY", "MISTRAL_API_KEY",
)


def _windows_user_env(name: str) -> str | None:
    """HKCU\\Environment value for name, or None. Never logged."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
    except OSError:
        return None
    return value if isinstance(value, str) else None


def load_user_env(read=None, env=None) -> list[str]:
    """Copy known keys missing from env (os.environ) out of the Windows User
    environment. Already-set vars are left alone. Returns the names copied."""
    env = os.environ if env is None else env
    if env.get("MEGAZWORD_NO_USER_ENV"):  # smoke/live-check: keys were removed on purpose
        return []
    if read is None:
        if os.name != "nt":
            return []
        read = _windows_user_env
    copied = []
    for name in USER_ENV_KEYS:
        if env.get(name):
            continue
        value = read(name)
        if value:
            env[name] = value
            copied.append(name)
    return copied


DEFAULT_SENTINEL_URLS = [
    "https://tahomatable.org",
    "https://hive-log.phone-liaison.workers.dev",
    "https://updawg.co",
]


@dataclass
class Config:
    agent: dict = field(default_factory=dict)
    rater_model: str = "qwen2.5:1.5b"
    route: dict[str, list[str]] = field(default_factory=lambda: dict(DEFAULT_ROUTE))
    grok: dict[str, tuple[str, str]] = field(default_factory=lambda: dict(DEFAULT_GROK))
    # B12: [claude.<level>], [codex.<level>], [gemini.<level>] model + effort. Empty = the
    # CLI's own default (Phil's Codex model stays unless he sets one).
    levels: dict[str, dict[str, tuple[str, str]]] = field(
        default_factory=lambda: {name: {} for name in ("claude", "codex", "gemini")})
    # Looked up when a Config is made (not at import) so tests can redirect HOME.
    log_path: Path = field(default_factory=lambda: HOME / "log.jsonl")
    # How many lines log.jsonl and each project's memory.jsonl keep ([limits]).
    log_lines: int = 5000
    memory_lines: int = 2000
    # AI name -> seconds to wait for an answer before giving up on it.
    timeouts: dict[str, int] = field(default_factory=dict)
    # Second-opinion check on auto-picked answers (local model). Off by default.
    quality_check: bool = False
    # [oneshot] lean: trim what routed one-shots load (MCP servers, skills,
    # settings files) using documented CLI flags. Safety flags are unaffected.
    lean: bool = True
    # AI name -> when its usage comes back. Set by hand for plans with no meter.
    out_until: dict[str, datetime] = field(default_factory=dict)
    free: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_FREE))
    room_primary: str = "workshop"
    room_turn_cap: int = 12
    room_name: str = "hive"
    sentinel_urls: list[str] = field(default_factory=lambda: list(DEFAULT_SENTINEL_URLS))
    ntfy_topic: str = ""
    healthchecks_url: str = ""

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
        # utf-8-sig: Notepad's "UTF-8 with BOM" would otherwise break parsing.
        data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
        cfg.rater_model = data.get("rater_model", cfg.rater_model)
        cfg.route.update(data.get("route", {}))
        cfg.quality_check = bool(data.get("quality_check", cfg.quality_check))
        oneshot = data.get("oneshot", {})
        if isinstance(oneshot, dict) and isinstance(oneshot.get("lean"), bool):
            cfg.lean = oneshot["lean"]
        cfg.out_until = {name: _as_time(v) for name, v in data.get("out", {}).items()}
        limits = data.get("limits", {})
        for key in ("log_lines", "memory_lines"):
            if isinstance(limits.get(key), int) and limits[key] > 0:
                setattr(cfg, key, limits[key])
        cfg.timeouts = {name: int(v) for name, v in data.get("timeouts", {}).items()
                        if isinstance(v, (int, float)) and v > 0}
        agent = data.get("agent", {})
        if not isinstance(agent, dict):
            raise ValueError("agent must be a table")
        for key, value in agent.items():
            if key in ("max_steps", "max_chars", "call_timeout", "wall_timeout", "test_timeout"):
                if type(value) is not int or value <= 0:
                    raise ValueError(f"agent.{key} must be a positive whole number")
            elif key == "text_protocol":
                if type(value) is not bool:
                    raise ValueError("agent.text_protocol must be true or false")
            elif key == "test_command":
                if not isinstance(value, list) or not value or not all(
                        isinstance(v, str) and v for v in value):
                    raise ValueError("agent.test_command must be a nonempty argv list")
                value = tuple(value)
            else:
                raise ValueError(f"unknown agent setting: {key}")
            cfg.agent[key] = value

        for name, block in data.get("free", {}).items():
            if name in cfg.free and isinstance(block, dict) and "model" in block:
                model = block["model"]
                if not isinstance(model, str) or not model.strip():
                    raise ValueError(f"free.{name}.model must be a nonempty string")
                cfg.free[name] = model.strip()

        for level, block in data.get("grok", {}).items():
            if isinstance(block, dict) and level in cfg.grok:
                model, effort = cfg.grok[level]
                cfg.grok[level] = (str(block.get("model", model)),
                                   str(block.get("effort", effort)))

        for name, table in cfg.levels.items():
            for level, block in (data.get(name) or {}).items():
                if level in DEFAULT_ROUTE and isinstance(block, dict):
                    table[level] = (str(block.get("model", "")).strip(),
                                    str(block.get("effort", "")).strip())

        room_block = data.get("room", {})
        if isinstance(room_block, dict):
            if "primary" in room_block and isinstance(room_block["primary"], str) and room_block["primary"].strip():
                cfg.room_primary = room_block["primary"].strip()
            if "turn_cap" in room_block and isinstance(room_block["turn_cap"], int) and room_block["turn_cap"] > 0:
                cfg.room_turn_cap = room_block["turn_cap"]
            if "name" in room_block and isinstance(room_block["name"], str) and room_block["name"].strip():
                cfg.room_name = room_block["name"].strip()
        sent = data.get("sentinel", {})
        if isinstance(sent, dict):
            urls = sent.get("urls")
            if isinstance(urls, list):
                cfg.sentinel_urls = [u.strip() for u in urls
                                     if isinstance(u, str) and u.strip().startswith("http")]
            if isinstance(sent.get("ntfy_topic"), str):
                cfg.ntfy_topic = sent["ntfy_topic"].strip()
            if isinstance(sent.get("healthchecks_url"), str):
                cfg.healthchecks_url = sent["healthchecks_url"].strip()
    return cfg


def render_default(installed: list[str]) -> str:
    """Render a commented config with only installed AIs in each route."""
    lines = ["# Local model used to rate each prompt's difficulty.",
             'rater_model = "qwen2.5:1.5b"', "", "# AIs to try, from first choice to last.", "[route]"]
    for level, names in DEFAULT_ROUTE.items():
        choices = [name for name in names if name in installed]
        values = ", ".join(f'"{name}"' for name in choices)
        lines.extend([f"# AIs to try for {level} tasks, in order.", f"{level} = [{values}]"])
    lines.extend([
        "",
        "# Sentinel production checks. ntfy_topic is filled by `megazword sentinel install`.",
        "[sentinel]",
        "urls = [" + ", ".join(f'"{u}"' for u in DEFAULT_SENTINEL_URLS) + "]",
        '# ntfy_topic = ""',
        '# healthchecks_url = ""',
    ])
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
    _set_key(path, "out", name, until.isoformat(timespec="seconds") if until else None)


# Serialize writers in the threaded dashboard, including out marks.
_WRITE_LOCK = threading.RLock()


def _statements(text: str):
    """Yield complete TOML statements without mistaking multiline values for tables."""
    start, chunk = 0, ""
    for line in text.splitlines(keepends=True):
        chunk += line
        try:
            parsed = tomllib.loads(chunk)
        except tomllib.TOMLDecodeError:
            continue
        yield start, start + len(chunk), chunk, parsed
        start += len(chunk)
        chunk = ""
    if chunk:
        raise ValueError("cannot safely locate config setting")


def _comments(value: str) -> list[str]:
    """Comments outside strings, including comments inside a multiline array."""
    comments, quote, i = [], None, 0
    while i < len(value):
        c = value[i]
        if quote:
            if c == "\\" and quote.startswith('"'):
                i += 2
                continue
            if value.startswith(quote, i):
                i += len(quote)
                quote = None
                continue
        elif c in "\"'":
            quote = c * 3 if value.startswith(c * 3, i) else c
            i += len(quote)
            continue
        elif c == "#":
            end = value.find("\n", i)
            end = len(value) if end < 0 else end
            comments.append(value[i:end].rstrip("\r"))
            i = end
        i += 1
    return comments


def _edit_key(text: str, table: str, key: str, value: str | None) -> str:
    """Preserve untouched bytes; refuse unusual layouts rather than rewrite them."""
    original = tomllib.loads(text)
    expected = deepcopy(original)
    target = expected.setdefault(table, {}) if table else expected
    if not isinstance(target, dict):
        raise ValueError(f"{table} must be a table")
    if value is None:
        if key not in target:
            return text
        del target[key]
    else:
        target[key] = tomllib.loads("value = " + value)["value"]
    newline = "\r\n" if "\r\n" in text else "\n"
    section, insert, hit = "", 0, None
    for start, end, chunk, parsed in _statements(text):
        stripped = chunk.lstrip()
        if stripped.startswith("["):
            # A header with quoted names/comments is parsed by TOML itself.
            probe = tomllib.loads(chunk + newline + "__mz_marker__ = true")
            path = []
            while isinstance(probe, dict) and "__mz_marker__" not in probe and len(probe) == 1:
                name, probe = next(iter(probe.items()))
                path.append(name)
            section = path[0] if len(path) == 1 and isinstance(probe, dict) else None
        if section == table:
            insert = end
            if key in parsed and not stripped.startswith("["):
                if len(parsed) != 1:
                    raise ValueError("cannot safely isolate config setting")
                hit = (start, end, chunk)
    if hit:
        start, end, chunk = hit
        # The keys we write are simple; accept quoted equivalents as well.
        match = re.match(r"(\s*(?:[A-Za-z0-9_-]+|\"[^\"]+\"|'[^']+')\s*=\s*)", chunk)
        if not match:
            raise ValueError("cannot safely isolate config setting")
        comments = _comments(chunk[match.end():])
        replacement = (match.group(1) + value if value is not None else "")
        if comments:
            replacement += (" " if replacement else "") + comments[0]
            replacement += "".join(newline + c for c in comments[1:])
        if chunk.endswith("\n") or comments:
            replacement += newline
        result = text[:start] + replacement + text[end:]
    elif value is not None:
        # Existing dotted/inline target layouts are intentionally refused below.
        entry = f"{key} = {value}{newline}"
        if table and table not in original:
            result = text + (newline if text and not text.endswith("\n") else "")
            result += f"{newline}[{table}]{newline}" + entry
        else:
            prefix = text[:insert]
            result = prefix + (newline if prefix and not prefix.endswith("\n") else "") + entry + text[insert:]
    else:
        raise ValueError("cannot safely isolate config setting")
    try:
        if tomllib.loads(result) != expected:
            raise ValueError("edit would change other config settings")
    except tomllib.TOMLDecodeError as exc:
        raise ValueError("cannot safely edit this TOML layout") from exc
    return result


def _atomic_replace(path: Path, data: bytes) -> None:
    """Same-directory temporary file: readers see either complete version."""
    fd, name = tempfile.mkstemp(prefix=".config-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _set_key(path: Path, table: str, key: str, value: str | None) -> None:
    # _WRITE_LOCK: dashboard threads; locked(): other megazword processes
    # (e.g. a run auto-marking an AI out while the dashboard saves settings).
    from .filelock import locked
    with _WRITE_LOCK, locked(path):
        old = path.read_bytes() if path.exists() else None
        bom = old is not None and old.startswith(b"\xef\xbb\xbf")
        text = old.decode("utf-8-sig") if old is not None else ""
        edited = _edit_key(text, table, key, value)
        if edited == text:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        replaced = False
        try:
            # Keep a byte-order mark if the file had one.
            _atomic_replace(path, (b"\xef\xbb\xbf" if bom else b"") + edited.encode("utf-8"))
            replaced = True
            load(path)  # Confirm the actual file through the application's loader.
        except Exception:
            if replaced:
                if old is None:
                    path.unlink(missing_ok=True)
                else:
                    _atomic_replace(path, old)
            raise


def _known_ai(name: str) -> None:
    from .backends import default_backends
    if not isinstance(name, str) or name not in default_backends():
        raise ValueError(f"unknown AI {name!r}")


def _positive_int(value, label: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{label} must be a positive whole number")


def set_route(level: str, names: list[str], path: Path | None = None) -> None:
    """Set one route, preserving order. An empty route is allowed."""
    if not isinstance(level, str) or level not in DEFAULT_ROUTE:
        raise ValueError("level must be easy, medium or hard")
    if not isinstance(names, list):
        raise ValueError("route must be a list of AI names")
    for name in names:
        _known_ai(name)
    if len(set(names)) != len(names):
        raise ValueError("route cannot contain duplicate AIs")
    _set_key(path or HOME / "config.toml", "route", level, json.dumps(names))


def set_timeout(ai: str, seconds: int | None, path: Path | None = None) -> None:
    """None removes the override and restores the backend's default timeout."""
    _known_ai(ai)
    if seconds is not None:
        _positive_int(seconds, "timeout")
    _set_key(path or HOME / "config.toml", "timeouts", ai,
             str(seconds) if seconds is not None else None)


def set_limit(name: str, n: int, path: Path | None = None) -> None:
    if not isinstance(name, str) or name not in ("log_lines", "memory_lines"):
        raise ValueError("limit must be log_lines or memory_lines")
    _positive_int(n, "line limit")
    _set_key(path or HOME / "config.toml", "limits", name, str(n))


def set_flag(name: str, value: bool, path: Path | None = None) -> None:
    if name != "quality_check" or type(value) is not bool:
        raise ValueError("quality_check must be true or false")
    _set_key(path or HOME / "config.toml", "", name, str(value).lower())
