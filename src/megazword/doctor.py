"""Read-only health checks for a Mega Zword installation."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import __version__, config, ollama, usage_sources


@dataclass
class Check:
    level: str
    name: str
    detail: str
    hint: str = ""

    def line(self) -> str:
        suffix = f"; {self.hint}" if self.hint else ""
        return f"{self.level} {self.name}: {self.detail}{suffix}"


def checks(home: Path | None = None) -> list[Check]:
    home = home or config.HOME
    found: list[Check] = []
    if sys.version_info >= (3, 11):
        found.append(Check("OK", "Python", sys.version.split()[0]))
    else:
        found.append(Check("FAIL", "Python", sys.version.split()[0],
                           "install Python 3.11 or newer"))
    found.append(Check("OK", "megazword", __version__))

    for name in ("claude", "codex", "grok"):
        path = shutil.which(name)
        if not path:
            found.append(Check("WARN", name, "not on PATH", f"install {name} or add it to PATH"))
            continue
        try:
            proc = subprocess.run([path, "--version"], capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=3)
            version = (proc.stdout or proc.stderr).strip().splitlines()
            if proc.returncode == 0 and version:
                found.append(Check("OK", name, version[0][:120]))
            else:
                found.append(Check("WARN", name, "found, version unavailable",
                                   f"check {name} --version"))
        except (OSError, subprocess.TimeoutExpired):
            found.append(Check("WARN", name, "found, version unavailable",
                               f"check {name} --version"))

    path = home / "config.toml"
    cfg = config.Config()
    if not path.exists():
        found.append(Check("WARN", "config", "missing", "run megazword init"))
    else:
        try:
            cfg = config.load(path)
            found.append(Check("OK", "config", "parses"))
        except Exception as exc:
            found.append(Check("FAIL", "config", type(exc).__name__,
                               "fix config.toml syntax and values"))
    active = cfg.out_now()
    found.append(Check("WARN" if active else "OK", "out marks",
                       ", ".join(sorted(active)) if active else "none active",
                       "review [out] in config.toml" if active else ""))
    from .backends import DEFAULT_TIMEOUT
    waits = ", ".join(f"{n} {cfg.timeouts.get(n, DEFAULT_TIMEOUT)}s"
                      for n in ("claude", "codex", "grok"))
    short = [n for n, t in cfg.timeouts.items() if t < 60]
    found.append(Check("WARN" if short else "OK", "timeouts", waits,
                       f"under 60s may cut off real work: {', '.join(short)}" if short else ""))
    known = {"claude", "codex", "grok"}
    unknown = sorted({name for route in cfg.route.values() for name in route
                      if name not in known})
    found.append(Check("WARN" if unknown else "OK", "routes",
                       ", ".join(unknown) if unknown else "known backends only",
                       "edit [route] in config.toml" if unknown else ""))

    if not ollama.reachable():
        found.append(Check("WARN", "Ollama", "unreachable", "start Ollama"))
        found.append(Check("WARN", "rater model", "cannot check while Ollama is offline",
                           f"start Ollama, then ollama pull {cfg.rater_model}"))
    else:
        found.append(Check("OK", "Ollama", "reachable"))
        try:
            present = cfg.rater_model in ollama.models()
            found.append(Check("OK" if present else "WARN", "rater model",
                               cfg.rater_model + (" present" if present else " missing"),
                               "ollama pull " + cfg.rater_model if not present else ""))
        except Exception:
            found.append(Check("WARN", "rater model", "could not list models",
                               "check Ollama /api/tags"))

    try:
        plans = usage_sources.all_usage(home / "log.jsonl")
        for plan in plans:
            found.append(Check("WARN" if plan.source == "error" else "OK",
                               f"{plan.service} meter",
                               "unreadable" if plan.source == "error" else "readable",
                               "check login or local meter files" if plan.source == "error" else ""))
    except Exception:
        found.append(Check("WARN", "usage meters", "unreadable",
                           "check login or local meter files"))

    log_path = home / "log.jsonl"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # Opening in append mode verifies permission without adding a log entry.
        with log_path.open("a", encoding="utf-8"):
            pass
        found.append(Check("OK", "log", "writable"))
    except OSError:
        found.append(Check("FAIL", "log", "not writable",
                           f"check permissions on {log_path}"))
    return found


def run() -> int:
    results = checks()
    for item in results:
        print(item.line())
    return 1 if any(item.level == "FAIL" for item in results) else 0
